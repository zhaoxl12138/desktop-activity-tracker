"""Shared presentation result after the existing evidence policy has run."""


def classification_result(base, final, policy, decision=None, *, revision=0,
                          captured_at='', application_type='desktop'):
    decision = decision or {}
    applied = (decision.get('apply') is True or
               (decision.get('apply') is None and decision.get('certainty') == 'high'))
    if applied and decision.get('category') == final:
        source = decision.get('source', 'AI')
    elif decision.get('status') == 'pending':
        source = 'AI待识别'
    elif decision:
        source = 'AI待确认'
    else:
        source = '兜底' if base in ('other','browser_general') else '规则'
    return {
        'source':source, 'base_category':base, 'final_category':final,
        'suggested_category':decision.get('suggested_category', decision.get('category','')),
        'certainty':decision.get('certainty',''), 'reason':decision.get('reason','') or
            ('未命中明确分类，使用兜底' if source == '兜底' else '命中本地分类规则'),
        'evidence':list(decision.get('evidence') or []), 'pattern_id':decision.get('pattern_id',''),
        'decision_revision':int(revision), 'effective_at':str(captured_at),
        'timing_policy_id':policy, 'application_type':application_type,
    }
