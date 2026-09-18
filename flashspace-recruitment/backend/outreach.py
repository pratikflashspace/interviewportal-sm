"""Candidate outreach on hiring decisions (approved 18 September 2026).

When the recruiter saves a hiring decision for an application (shortlisted,
contacted, hired, rejected), the candidate is notified by email and WhatsApp.

Providers (env-driven, off until configured — same pattern as ClickUp):
- Email: any SMTP server. SMTP_HOST/PORT/USER/PASSWORD, OUTREACH_EMAIL_FROM.
  Works with Gmail app passwords, Zoho, Brevo, Resend SMTP, etc.
- WhatsApp: Meta WhatsApp Cloud API. WHATSAPP_TOKEN + WHATSAPP_PHONE_ID.
  Outbound-first business messages MUST use a pre-approved template
  (WHATSAPP_TEMPLATE_NAME); plain text only works inside the 24-hour
  customer-service window, so template mode is the default when configured.

Safety rules:
- Idempotent: one message per application per stage; re-saving the same
  stage never re-sends. A new decision stage sends again.
- Best-effort: an outreach failure never blocks the recruiter's decision;
  the result is reported in the API response and can be retried by
  saving the stage again after fixing configuration.
- No candidate content leaves the system beyond the notification itself.
"""
import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage
from .server import APIError, now

# settings key prefix for idempotency: outreach:<application_id>
OUTREACH_KEY = 'outreach:'
EMAIL_TIMEOUT = 15
WHATSAPP_TIMEOUT = 15

STAGE_SUBJECTS = {
    'shortlisted': 'Update on your application — {role}',
    'contacted': 'Your application for {role} — next steps',
    'hired': 'Congratulations — your application for {role}',
    'rejected': 'Update on your application — {role}',
}

STAGE_BODIES = {
    'shortlisted': ('Hi {name},\n\nGood news — your application for {role} at Stirring Minds has been '
                    'shortlisted. Our team will be in touch with you about the next steps.\n\n'
                    '{note}Warm regards,\nTeam Stirring Minds'),
    'contacted': ('Hi {name},\n\nThank you for interviewing with us for {role}. We would like to discuss '
                  'your application — please expect a call or email from our team shortly.\n\n'
                  '{note}Warm regards,\nTeam Stirring Minds'),
    'hired': ('Hi {name},\n\nCongratulations! We are delighted to move forward with you for {role} at '
              'Stirring Minds. Our team will contact you with the details and next steps.\n\n'
              '{note}Warm regards,\nTeam Stirring Minds'),
    'rejected': ('Hi {name},\n\nThank you for taking the time to apply and interview for {role} with '
                 'Stirring Minds. After careful review, we have decided not to move forward with your '
                 'application at this time. We appreciate your interest and wish you the very best.\n\n'
                 '{note}Warm regards,\nTeam Stirring Minds'),
}

WHATSAPP_TEXTS = {
    'shortlisted': 'Hi {name}! Good news — your application for {role} at Stirring Minds has been shortlisted. Our team will contact you about next steps.',
    'contacted': 'Hi {name}! Thank you for interviewing with us for {role}. Our team would like to discuss your application and will contact you shortly.',
    'hired': 'Hi {name}! Congratulations — we are delighted to move forward with you for {role} at Stirring Minds. We will contact you with the details.',
    'rejected': 'Hi {name}. Thank you for applying and interviewing for {role} with Stirring Minds. After careful review we will not move forward at this time. We wish you the very best.',
}


def _env(name):
    value = os.getenv(name, '').strip()
    return value or None


def smtp_configured():
    return bool(_env('SMTP_HOST') and _env('SMTP_USER') and _env('SMTP_PASSWORD'))


def whatsapp_configured():
    return bool(_env('WHATSAPP_TOKEN') and _env('WHATSAPP_PHONE_ID'))


def _send_email(to_email, subject, body):
    host = _env('SMTP_HOST')
    port = int(_env('SMTP_PORT') or '587')
    user = _env('SMTP_USER')
    password = _env('SMTP_PASSWORD')
    sender = _env('OUTREACH_EMAIL_FROM') or user
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = f'Teamrecrut <{sender}>'
    msg['To'] = to_email
    msg.set_content(body)
    with smtplib.SMTP(host, port, timeout=EMAIL_TIMEOUT) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


def _send_whatsapp(phone, text, name):
    """Meta WhatsApp Cloud API. Template mode when configured, else text."""
    token = _env('WHATSAPP_TOKEN')
    phone_id = _env('WHATSAPP_PHONE_ID')
    template = _env('WHATSAPP_TEMPLATE_NAME')
    url = f'https://graph.facebook.com/v21.0/{phone_id}/messages'
    if template:
        payload = {'messaging_product': 'whatsapp', 'to': phone, 'type': 'template',
                   'template': {'name': template, 'language': {'code': _env('WHATSAPP_TEMPLATE_LANG') or 'en'},
                               'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': text}]}]}}
    else:
        payload = {'messaging_product': 'whatsapp', 'to': phone, 'type': 'text', 'text': {'body': text}}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method='POST',
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=WHATSAPP_TIMEOUT) as r:
        json.loads(r.read().decode() or '{}')


def _setting(store, key):
    with store.db() as db:
        row = db.execute('SELECT data FROM workspace_records WHERE key=?', (key,)).fetchone()
    return json.loads(row['data']) if row else None


def _save_setting(store, key, data):
    with store.db() as db:
        db.execute('INSERT INTO workspace_records(key,data,version) VALUES (?,?,1) '
                   'ON CONFLICT(key) DO UPDATE SET data=excluded.data,version=workspace_records.version+1',
                   (key, json.dumps(data)))


def notify_decision(app, application, stage, note=''):
    """Send email + WhatsApp for a hiring decision. Idempotent per stage.

    Returns a status dict for the recruiter. Never raises: every failure is
    reported in the result so the decision itself is never blocked.
    """
    result = {'stage': stage, 'email': None, 'whatsapp': None, 'already_sent': False}
    key = OUTREACH_KEY + application['id']
    sent = _setting(app.store, key)
    if sent and sent.get('stage') == stage and sent.get('complete'):
        result['already_sent'] = True
        result['email'] = sent.get('email')
        result['whatsapp'] = sent.get('whatsapp')
        return result

    name = application['name']
    role = application['role_title']
    email_addr = application.get('email')
    phone = None
    try:
        with app.store.db() as db:
            row = db.execute('SELECT data FROM workspace_profiles WHERE user_id=?', (application['user_id'],)).fetchone()
        if row:
            profile = json.loads(row['data'])
            value = profile.get('phone') or profile.get('personal', {}).get('phone')
            if isinstance(value, str) and value.isdigit() and len(value) == 10:
                phone = value
    except Exception:
        phone = None

    formatted_note = f'{note.strip()}\n\n' if isinstance(note, str) and note.strip() else ''
    status = {}

    if stage in STAGE_BODIES and email_addr and smtp_configured():
        try:
            body = STAGE_BODIES[stage].format(name=name, role=role, note=formatted_note)
            _send_email(email_addr, STAGE_SUBJECTS[stage].format(role=role), body)
            status['email'] = 'sent'
        except Exception as exc:
            status['email'] = 'failed: ' + str(exc)[:120]
    else:
        status['email'] = 'sent' if stage not in STAGE_BODIES else (
            'skipped: no email address' if not email_addr else 'skipped: email not configured')

    if stage in WHATSAPP_TEXTS and phone and whatsapp_configured():
        try:
            text = WHATSAPP_TEXTS[stage].format(name=name.split(' ')[0], role=role)
            if formatted_note:
                text += ' Note: ' + note.strip()[:300]
            _send_whatsapp(phone, text, name)
            status['whatsapp'] = 'sent'
        except Exception as exc:
            status['whatsapp'] = 'failed: ' + str(exc)[:120]
    else:
        status['whatsapp'] = 'sent' if stage not in WHATSAPP_TEXTS else (
            'skipped: no phone number' if not phone else 'skipped: WhatsApp not configured')

    complete = all(not v.startswith('failed') for v in status.values())
    _save_setting(app.store, key, {'stage': stage, 'sent_at': now(), 'complete': complete, **status})
    result.update(status)
    return result
