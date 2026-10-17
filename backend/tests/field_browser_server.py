"""Local browser-test server with synthetic analysis. Never uses a model or patient data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_review import rich_result
from test_analysis import FakeAdapter, runtime
from test_api import pdf_bytes
from backend.app import create_app
import uvicorn

if __name__ == '__main__':
    Path('/tmp/merged-synthetic.pdf').write_bytes(pdf_bytes(3))
    uvicorn.run(create_app(ocr=lambda image: 'Synthetic OCR', analysis=runtime(FakeAdapter(rich_result))),
                host='127.0.0.1', port=8001, access_log=False)
