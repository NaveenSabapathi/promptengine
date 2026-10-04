from promptengine import create_app
from promptengine.environment import load_file_secrets

load_file_secrets()
app = create_app()
