import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app import create_app
if not os.environ.get('EVENT_TEST_DATABASE'):raise RuntimeError('Provide a disposable EVENT_TEST_DATABASE.')
app=create_app({'DATABASE':os.environ['EVENT_TEST_DATABASE'],'SECRET_KEY':'browser-test-only'})
r=app.test_cli_runner().invoke(args=['init-admin','--username','organiser','--password','browser-test-password'])
if r.exit_code:raise RuntimeError(r.output)
app.run(host='127.0.0.1',port=5000)
