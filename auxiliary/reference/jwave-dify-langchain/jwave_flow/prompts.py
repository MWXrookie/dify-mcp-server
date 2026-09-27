"""All LLM prompts, extracted **verbatim** from the Dify workflow
``dify_workflow/仿真.yml`` (only the ``{{#node.var#}}`` references were
rewritten into Python ``str.format`` placeholders).

Do not hand-edit: regenerate/verify with ``tests/test_prompts_match_dify.py``.
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

# node ids in the original Dify graph are kept in comments for traceability
REQUIREMENT_ANALYST_SYSTEM = ''
REQUIREMENT_ANALYST_USER = '\n\xa0\xa0\xa0 你是一个声学仿真需求分析师。你的任务是将用户的自然语言输入整理成结构化的仿真需求描述。\n\xa0\xa0\xa0 阅读用户输入：{query}，提取并整理以下信息：\n\xa0\xa0\xa0 1. 仿真类型？\n\xa0\xa0\xa0 2. 涉及介质？\n\xa0\xa0\xa0 3. 声源类型与频率？\n\xa0\xa0\xa0 4. 有无障碍物？\n\xa0\xa0\xa0 5. 仿真区域？\n\xa0\xa0\xa0 6. 期望输出？\n\xa0\xa0\xa0\xa0\xa0\xa0 注意：如果用户没提，请根据常识进行合理猜测，输出一段通顺的需求描述。\n\xa0'  # node 1783990970058 (LLM / 需求分析)

PARAM_EXTRACT_USER = '你是一个 jwave 声学仿真参数提取器。根据用户需求和知识库内容，提取 JSON 参数。\n\xa0\n用户需求：{query}\n知识库参考：{kb_context}\n\xa0\n请严格按照结构化输出中定义的 JSON Schema 输出，只输出 JSON，不要有其他解释。'  # node 1783991048409 (参数提取)

CODE_GENERATE_USER = '你是 jwave Python 代码生成器。\n\xa0\n任务：\n\xa0\n根据参考代码生成最终代码。\n\xa0\n规则：\n\xa0\n1. 必须保持参考代码结构不变。\n2. 只允许修改：\n\xa0\xa0 - sound_speed\n\xa0\xa0 - density\n\xa0\xa0 - source_frequency\n\xa0\xa0 - t_end\n\xa0\xa0 - positions\n\xa0\n3. 不允许新增函数。\n4. 不允许删除函数。\n5. 不允许修改变量名称。\n6. 不允许修改参数顺序。\n7. 不允许修改 API 调用方式。\n\xa0\n\xa0\n用户需求：\n\xa0\n{query}\n\n代码参考：\n{code_ref}\n\xa0\n输出要求：\n\xa0\n仅输出完整 Python 代码。\n\xa0\n禁止输出：\n\xa0\n<think>\n</think>\nENDTHINKFLAG\nMarkdown\n解释\n分析\n自然语言\n\xa0\n输出内容必须从代码第一行开始，到代码最后一行结束。'  # node 1783991079665 (代码生成)

CODE_FIX_USER = '你是一个代码改正器。\n\n你会收到三段输入：\n- 需要改正的代码：{code_final}\n- 可用辅助信息：{context}\n- 代码的报错：{stderr}\n\n你的唯一任务是：修复代码错误，并返回修复后的完整代码。\n\n# 最重要规则：\n**输出必须是代码格式，要求能完成运行**\n\n# 严格规则：\n1. 只输出最终修复后的完整代码。\n2. 不输出任何解释、分析、注释说明、步骤、标题、前后缀文本。\n3. 不使用 Markdown 代码块包裹（不要 ```）。\n4. 保持原有功能不变，仅做修复错误所必需的最小改动。\n5. 必须结合“可用辅助信息”进行修复，不得臆造不存在的库、函数、参数。\n6. 如果有多种修复方式，选择最稳健且兼容原逻辑的一种。\n7. 输出必须是可直接替换原代码的版本。'  # node 1784023398114 (代码纠错)

TEMPLATE_TRANSFORM = '{% for item in arg1 %}\r\n{{ item.content }}\r\n{% endfor %}\r\n'  # node 1783990989034 (模板转换)



def requirement_analyst_prompt() -> ChatPromptTemplate:
    """① 需求分析 — turn the raw query into a structured requirement."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", REQUIREMENT_ANALYST_SYSTEM),
            ("human", REQUIREMENT_ANALYST_USER),
        ]
    )


def param_extract_prompt() -> ChatPromptTemplate:
    """④ 参数提取 — pull JSON parameters out of query + knowledge base."""
    return ChatPromptTemplate.from_messages([("human", PARAM_EXTRACT_USER)])


def code_generate_prompt() -> ChatPromptTemplate:
    """⑤ 代码生成 — write the jwave script from the reference code."""
    return ChatPromptTemplate.from_messages([("human", CODE_GENERATE_USER)])


def code_fix_prompt() -> ChatPromptTemplate:
    """⑦ 代码纠错 — repair a script given its stderr."""
    return ChatPromptTemplate.from_messages([("human", CODE_FIX_USER)])
