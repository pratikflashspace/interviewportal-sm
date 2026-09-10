"""Pure versioned two-stage engine: deterministic replay and bounded follow-ups."""
import copy
import random
import re
from .v2_banks import GENERIC, BANKS, BANK_VERSION


class FlowError(ValueError):
    pass


def create_flow(bank_key, seed):
    if bank_key not in BANKS:
        raise FlowError('This role needs an approved domain question bank.')
    rng = random.Random(seed)
    bank = BANKS[bank_key]
    selected = copy.deepcopy(GENERIC + rng.sample([q for q in bank if q['category']=='fundamental'], 2)
                            + rng.sample([q for q in bank if q['category']=='scenario'], 2))
    for q in selected:
        q.update(kind='core', parent_id=None)
    return {'flow_version': 2, 'bank_version': BANK_VERSION, 'bank_key': bank_key,
            'selected': selected, 'core_index': 0, 'active': copy.deepcopy(selected[0]),
            'followups': {'generic': 0, 'domain': 0}, 'answers': [], 'version': 0,
            'status': 'interview', 'pending_decision': None}


def similar(a, b):
    aa, bb = set(re.findall(r'\w+', a.lower())), set(re.findall(r'\w+', b.lower()))
    return bool(aa and bb) and len(aa & bb)/len(aa | bb) >= .72


def commit_answer(flow, event_id, expected_version, question_id, transcript, stamp):
    if not isinstance(event_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', event_id):
        raise FlowError('Invalid answer event.')
    if not isinstance(transcript, str) or not 1 <= len(transcript.strip()) <= 6000:
        raise FlowError('Answer must contain 1 to 6000 characters.')
    answer = transcript.strip()
    for previous in flow['answers']:
        if previous['event_id'] == event_id:
            if previous['question_id'] != question_id or previous['answer'] != answer:
                raise FlowError('An answer event cannot be reused with different content.')
            return copy.deepcopy(flow), False
    if flow['pending_decision'] is not None:
        raise FlowError('Wait for the next saved question.')
    active = flow['active']
    if flow['status'] != 'interview' or not active:
        raise FlowError('Interview is complete.')
    if type(expected_version) is not int or expected_version != flow['version'] or question_id != active['id']:
        raise FlowError('Interview state changed. Reload before answering.')
    result = copy.deepcopy(flow)
    result['answers'].append({'event_id': event_id, 'question_id': active['id'], 'question': active['text'],
        'answer': answer, 'at': stamp, 'stage': active['stage'], 'kind': active['kind'],
        'category': active['category'], 'parent_id': active['parent_id'], 'flow_version': 2})
    result['version'] += 1
    result['pending_decision'] = copy.deepcopy(active)
    result['active'] = None
    return result, True


def resolve_next(flow, followup_index=None):
    result = copy.deepcopy(flow)
    parent = result['pending_decision']
    if parent is None:
        return result
    options = parent.get('followups', [])
    use = (parent['kind']=='core' and result['followups'][parent['stage']] < 2
           and type(followup_index) is int and 0 <= followup_index < len(options))
    if use:
        question = options[followup_index]
        use = not any(similar(question, a['question']) for a in result['answers'])
    if use:
        result['active'] = {**parent, 'id': parent['id']+'-followup', 'text': question,
                            'kind': 'followup', 'parent_id': parent['id'], 'followups': []}
        result['followups'][parent['stage']] += 1
    else:
        result['core_index'] += 1
        result['active'] = (copy.deepcopy(result['selected'][result['core_index']])
                            if result['core_index'] < len(result['selected']) else None)
        if result['active'] is None:
            result['status'] = 'completed'
    result['pending_decision'] = None
    return result


def public_flow(flow):
    active = flow['active']
    return {'flow_version': 2, 'bank_version': flow['bank_version'], 'bank_key': flow['bank_key'],
            'version': flow['version'], 'status': flow['status'], 'answers': flow['answers'],
            'core_total': 10, 'core_index': flow['core_index'], 'max_turns': 14,
            'active': {k: active[k] for k in ('id','text','stage','kind','category','parent_id')} if active else None,
            'processing': flow['pending_decision'] is not None}
