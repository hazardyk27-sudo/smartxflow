from .config import OrchestratorConfig
from .llm_client import OpenAIResponsesClient
from .server import create_app
from .store import SQLiteOrchestratorStore
from .strict_service import StrictPredictorOrchestrator


config = OrchestratorConfig.from_env(require_secrets=True, require_api_key=False)
store = SQLiteOrchestratorStore(config.state_db_path)
llm = OpenAIResponsesClient(config)
orchestrator = StrictPredictorOrchestrator(config=config, store=store, llm=llm)

app = create_app(config=config, orchestrator=orchestrator)
