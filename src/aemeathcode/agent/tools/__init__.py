from aemeathcode.agent.tools.builtin.bash_tool import BashTool
from aemeathcode.agent.tools.builtin.list_dir_tool import ListDirTool
from aemeathcode.agent.tools.builtin.read_file_tool import ReadFileTool
from aemeathcode.agent.tools.builtin.task_create_tool import TaskCreateTool
from aemeathcode.agent.tools.builtin.task_get_tool import TaskGetTool
from aemeathcode.agent.tools.builtin.task_list_tool import TaskListTool
from aemeathcode.agent.tools.builtin.task_update_tool import TaskUpdateTool
from aemeathcode.agent.tools.builtin.write_file_tool import WriteFileTool
from aemeathcode.agent.tools.builtin.note_save_tool import NoteSaveTool
from aemeathcode.agent.tools.registry import ToolRegistry


registry = ToolRegistry()
registry.register(ReadFileTool())
registry.register(ListDirTool())
registry.register(WriteFileTool())
registry.register(BashTool())
registry.register(TaskGetTool())
registry.register(TaskCreateTool())
registry.register(TaskListTool())
registry.register(TaskUpdateTool())
registry.register(NoteSaveTool())