"""Save each turn before calling an AI provider. Caller holds the app lock.

A standard, visibly labelled follow-up is committed with the answer first.
This keeps the existing frontend usable after provider failure or process exit.
No raw audio or provider error detail is persisted by this module.
"""
import logging

LOG = logging.getLogger('flashspace')


def standard_question(role, answered):
    title = role['title']
    prompts = {
        1: f'For {title}, describe a difficult work problem. What steps did you take and why?',
        2: f'In {title}, how would you prioritize two urgent tasks with limited time? Explain your reasoning.',
        3: f'For {title}, what measures would you use to check whether your work improved the outcome?',
    }
    return 'Standard follow-up: ' + prompts[answered]


def save_answer(app, application_id, user_id, body, error_type, validate_text, timestamp):
    """Return a stored application; never acknowledge an uncommitted answer.

    Provider errors use the already-committed standard question. Database errors
    propagate: a failed first commit prevents inference and any success response.
    Identical retries return the existing record without spending AI quota.
    """
    a = app.store.get(application_id)
    if a['user_id'] != user_id:
        raise error_type(404, 'Application not found.')
    if not isinstance(body, dict):
        raise error_type(400, 'Invalid request body.')
    answer = validate_text(body, 'answer', 10, 6000)
    turn = body.get('turn')
    if type(turn) is not int:
        raise error_type(400, 'Invalid interview turn.')
    if 0 <= turn < len(a['answers']) and a['answers'][turn]['answer'] == answer:
        return a
    if a['status'] == 'completed' or len(a['answers']) >= 4:
        raise error_type(409, 'This interview is already complete.')
    if turn != len(a['answers']):
        raise error_type(409, 'This question was already answered. Reopen My applications to resume.')
    if not isinstance(a.get('question'), str) or not a['question'].strip():
        raise error_type(409, 'No question is ready. Reopen My applications to resume.')

    a['answers'] = [*a['answers'], {
        'question': a['question'], 'answer': answer, 'at': timestamp(),
    }]
    answered = len(a['answers'])
    a['question'] = standard_question(a['role_snapshot'], answered) if answered < 4 else None
    a['question_source'] = 'standard' if answered < 4 else 'complete'
    a = app.store.save(a)
    if answered == 4:
        return a

    try:
        app.ai_quota(a, 'question', 20)
        question = app.ai.next_question(a['role_snapshot'], a['answers'])
        if not isinstance(question, str) or not 10 <= len(question) <= 650:
            raise error_type(502, 'Invalid generated question.')
    except Exception:
        # Never log answers, credentials, provider response bodies or exception text.
        LOG.warning('question_generation_unavailable; committed_standard_question_used')
        return a

    a['question'] = question
    a['question_source'] = 'ai'
    # Outside the provider catch: database failures must not appear successful.
    return app.store.save(a)
