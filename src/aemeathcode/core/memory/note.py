from pathlib import Path

class NoteStore:
    def __init__(self,base_dir:Path):
        self.base_dir = base_dir

    def append(self,content:str):
        file_path = self.base_dir /"note.md"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("a", encoding="utf-8") as file:
            file.write(f"- {content}\n")

    def load(self) -> list[str]:
        file_path = self.base_dir / "note.md"

        if not file_path.exists():
            return []

        with file_path.open("r", encoding="utf-8") as file:
            notes = []

            for line in file:
                line = line.strip()

                if line.startswith("- "):
                    notes.append(line[2:])

            return notes