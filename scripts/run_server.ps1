Set-Location "C:\Users\Admin\Documents\Proyectos\monitoreo_agente_reg"
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload *> uvicorn.log
