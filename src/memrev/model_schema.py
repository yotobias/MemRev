"""Wire schemas for automated extraction and judgments; existing validators decide acceptance."""

import copy

from memrev.evaluation import PROTOCOL, _evaluate, _rows_by_id
from memrev.provenance import _fields


def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def array_schema(items):
    return {'type': 'array', 'items': items}


def choice(values):
    return {'type': 'string', 'enum': list(values)}


TEXT = {'type': 'string'}
NULLABLE_TEXT = {'type': ['string', 'null']}
INDICES = array_schema({'type': 'integer'})
ASSUMPTION_SCHEMA = object_schema({
    'statement': TEXT, 'symbol': NULLABLE_TEXT, 'file': NULLABLE_TEXT,
    'predicate': choice(['returns', 'raises', 'accepts', 'mutates', 'calls', 'type_is', 'default_is', 'other']),
    'kind': choice(['repo_behaviour', 'procedure', 'environment']),
    'scope': object_schema({key: NULLABLE_TEXT for key in ['inputs', 'config', 'env']}),
    'evidence_message_indices': INDICES,
    'evidence_basis': choice(['execution_observation', 'code_observation', 'unverified_assertion', 'no_evidence']),
    'workspace_context': TEXT,
})
EXTRACTION_SCHEMA = object_schema({
    'schema_version': {'type': 'integer', 'enum': [2]},
    'lessons': array_schema(object_schema({'advice': TEXT, 'from_failed_step': {'type': ['boolean', 'null']},
                                         'assumptions': array_schema(ASSUMPTION_SCHEMA)})),
})


def judgment_schema(assumption=False):
    fields = {'outcome': choice(PROTOCOL['assumption_outcome_definitions' if assumption else 'lesson_outcome_definitions']),
              'issue_codes': array_schema(choice(PROTOCOL['issue_definitions'])), 'reason': TEXT,
              'reviewer_evidence_message_indices': INDICES}
    if assumption:
        fields['rubric'] = object_schema({key: choice(PROTOCOL['rating_values']) for key in PROTOCOL['rubric_definitions']})
    return object_schema(fields)


REVIEW_SCHEMA = object_schema({'lessons': array_schema(object_schema({
    'lesson_id': TEXT, 'evaluation': judgment_schema(),
    'assumptions': array_schema(object_schema({'assumption_id': TEXT, 'evaluation': judgment_schema(True)})),
}))})


def assemble_review(record, draft, judgments):
    """Attach only model judgments to immutable originals; never let a model invent attribution."""
    _fields(judgments, ['lessons'], 'judgments')
    rows = _rows_by_id(judgments['lessons'], draft['lessons'], 'lesson_id', 'judgments.lessons')
    review = copy.deepcopy(draft)
    for lesson in review['lessons']:
        row = rows[lesson['lesson_id']]
        _fields(row, ['lesson_id', 'evaluation', 'assumptions'], 'judgment.lesson')
        lesson['evaluation'] = row['evaluation']
        assumptions = _rows_by_id(row['assumptions'], lesson['assumptions'], 'assumption_id', 'judgments.assumptions')
        for assumption in lesson['assumptions']:
            value = assumptions[assumption['assumption_id']]
            _fields(value, ['assumption_id', 'evaluation'], 'judgment.assumption')
            assumption['evaluation'] = value['evaluation']
    _evaluate(record, review)
    return review
