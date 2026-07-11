from aemeathcode.agent.tools.builtin.list_dir_tool import ListDirTool
from aemeathcode.agent.tools.builtin.read_file_tool import ReadFileTool
from aemeathcode.agent.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.register(ReadFileTool())
registry.register(ListDirTool())
