from aemeathcode.agent.tools.base import BaseTool, ToolResult


class UseSkillTool(BaseTool):
    name = "use_skill"
    description = ("加载一个技能(skill):把某个已定义流程的完整说明拉进来照着做。"
                  "可用技能清单见系统提示的「可用技能」一节;遇到匹配的流程性任务就先加载对应 skill 再动手。")
    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "要加载的技能名(见「可用技能」清单)"
            }
        },
        "required": ["name"]
    }

    async def invoke(self, params, ctx) -> ToolResult:
        skill = ctx.services.skill_store.get(params["name"])
        if skill is None:
            available = ", ".join(ctx.services.skill_store.names()) or "(无)"
            return ToolResult(content=f"没有名为 {params['name']} 的技能。可用:{available}",
                              is_error=True, error_type="unknown_skill")
        return ToolResult(content=skill.body, is_error=False)
