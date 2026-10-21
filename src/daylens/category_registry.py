"""Single category vocabulary; matching rules remain in the existing config."""
from dataclasses import dataclass, replace

TIMING_POLICIES = {'interactive_required': '主动交互型', 'passive_allowed': '被动消费型'}


@dataclass(frozen=True)
class CategoryDefinition:
    id: str
    name: str
    group: str
    color: str
    timing_policy: str = 'interactive_required'
    ai_allowed: bool = True
    manual_allowed: bool = True
    aliases: tuple = ()
    display_order: int = 0


_BUILTINS = (
    CategoryDefinition('coding', '技术学习 / 开发', 'work', 'coding_green'),
    CategoryDefinition('reading', '阅读学习', 'work', 'reading_blue'),
    CategoryDefinition('office', '办公 / 求职', 'work', 'coding_green'),
    CategoryDefinition('ai_tools', 'AI工具', 'work', 'ai_blue'),
    CategoryDefinition('creative', '设计创作', 'work', 'creative_pink'),
    CategoryDefinition('social', '社交通讯', 'social', 'social_purple', 'passive_allowed'),
    CategoryDefinition('tools', '系统工具', 'tools', 'tools_cyan', aliases=('system_tools',)),
    CategoryDefinition('gaming', '游戏娱乐', 'entertainment', 'video_orange'),
    CategoryDefinition('finance', '投资理财', 'finance', '#D8B45B'),
    CategoryDefinition('video', '影音娱乐', 'entertainment', 'video_orange', 'passive_allowed'),
    CategoryDefinition('browser_general', '浏览器', 'browser_general', 'browser_amber', aliases=('browser_other',)),
    CategoryDefinition('other', '其他', 'other', 'other_teal'),
    CategoryDefinition('work', '工作学习', 'work', 'coding_green', ai_allowed=False, manual_allowed=False),
    CategoryDefinition('entertainment', '娱乐休闲', 'entertainment', 'video_orange', ai_allowed=False, manual_allowed=False),
    CategoryDefinition('idle', '空闲', 'idle', 'idle_gray', ai_allowed=False, manual_allowed=False, aliases=('idle_leave','hangup')),
)


def category_definitions(config_categories=None):
    categories = config_categories or {}
    result = []
    for definition in _BUILTINS:
        config = categories.get(definition.id, {})
        policy = config.get('active_rule', definition.timing_policy)
        if policy not in TIMING_POLICIES:
            raise ValueError('不支持的计时策略')
        result.append(replace(definition, name=config.get('display_name') or definition.name, timing_policy=policy))
    known = {d.id for d in result} | {a for d in result for a in d.aliases}
    for key, config in categories.items():
        if key in known:
            continue
        policy = config.get('active_rule', 'interactive_required')
        if policy not in TIMING_POLICIES:
            raise ValueError('不支持的计时策略')
        result.append(CategoryDefinition(key, config.get('display_name') or key, key,
                                         'other_teal', policy, ai_allowed=False))
    return tuple(replace(d, display_order=index) for index,d in enumerate(result))


def category_choices(config_categories=None):
    return tuple((d.name, d.id) for d in category_definitions(config_categories) if d.manual_allowed)


def category_definition(key, config_categories=None):
    return next((d for d in category_definitions(config_categories) if key == d.id or key in d.aliases), None)


def group_keys(group):
    return {key for d in _BUILTINS if d.group == group for key in (d.id, *d.aliases)}


AI_CATEGORY_IDS = frozenset(d.id for d in _BUILTINS if d.ai_allowed)
RULE_PRIORITY_IDS = ('finance','ai_tools','coding','office','reading','video','creative','gaming',
                     'social','tools','browser_general','other','idle_leave')
