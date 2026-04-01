from celery import Celery
import os

broker_url = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
result_backend = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

celery_app = Celery(
    'livros_narrados_worker',
    broker=broker_url,
    backend=result_backend,
    include=['worker.tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Sao_Paulo',
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10
)
