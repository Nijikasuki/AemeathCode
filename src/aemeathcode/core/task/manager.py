from aemeathcode.core.task.model import Task


class TaskManager:
    def __init__(self):
        self._tasks = {}
        self._next_task_id = 1

    def create(self, content)->Task:
        task = Task(id=self._next_task_id, content=content,status="pending")
        self._tasks[task.id] = task
        self._next_task_id += 1
        return task

    def list(self)->list[Task]:
        return list(self._tasks.values())

    def get(self,task_id)->Task|None:
        return self._tasks.get(task_id)

    def update(self, task_id:int, status:str)->Task|None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task.status = status
        return task