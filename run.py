from dotenv import load_dotenv
load_dotenv()

import logging
from app import create_app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logging.getLogger('PhaseLogger').setLevel(logging.INFO)

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)