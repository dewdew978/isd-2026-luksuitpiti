import sys
from pathlib import Path
import importlib.util

# Set repository root (project directory)
repo_root = Path(__file__).resolve().parent
sys.path.append(str(repo_root))

# Load configuration
from lab10_fastapi.curriculum_app.config import Settings
config = Settings()

# Dynamically load lab8b module
lab8b_path = repo_root / 'src' / 'ocr_system' / 'lab8b_curriculum_db.py'
spec = importlib.util.spec_from_file_location('lab8b', str(lab8b_path))
lab8b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab8b)

# Import model service and database
from lab10_fastapi.curriculum_app.model_service import QwenTextToSQL
from lab10_fastapi.curriculum_app.database import CurriculumDatabase

# Instantiate service and database
service = QwenTextToSQL(config, lab8b)
db = CurriculumDatabase(lab8b, config.db_path, config.max_rows)

# Sample query
question = "หลักสูตร IT มีหน่วยกิตกี่หน่วย?"
result = service.ask(db, question)
print(result)
