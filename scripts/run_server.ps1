Set-Location "C:\Users\MarceloThompson\Documents\Programación\monitoreo_agente_reg"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 *> uvicorn.log
