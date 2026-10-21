"""Shared privacy boundary for classification and report evidence."""
from .intelligence_state import title_context


def privacy_revision(_settings):
    # Keep the original empty-policy digest so existing non-excluded cache stays valid.
    return '7b75d8ad681b2ac055618656fbc721b8a8c03f750c00800935e21e12358cfb72'


def classification_payload(rows, settings):
    result = []
    for row in rows:
        context = title_context(row.get('app'), row.get('title'), settings, 'outbound')
        if context is None:
            continue
        item = {key:row[key] for key in ('id','base_category','active_seconds') if key in row}
        item.update(app=context['app'], title=context['title'])
        recent = []
        for prior in row.get('recent_titles', []):
            safe = title_context(prior.get('app'), prior.get('title'), settings, 'outbound')
            if safe and safe['app'] == context['app']:
                recent.append({**safe, **{key:prior[key] for key in ('active_seconds','confirmed_category') if key in prior}})
        # Recent item fingerprints are local implementation details.
        item['recent_titles'] = [{k:v for k,v in prior.items() if k != 'id'} for prior in recent[-5:]]
        result.append(item)
    return result


def report_facts(facts, settings):
    result = []
    for fact in facts:
        if 'title' not in fact:
            result.append(fact)
            continue
        context = title_context(fact.get('app'), fact.get('title'), settings, 'outbound')
        if context:
            result.append({k:v for k,v in dict(fact, app=context['app'], title=context['title']).items()
                           if k != 'session_refs'})
    return result
