# django-learning

A simple Django project for learning and experimentation.
## Prerequisites

- Python 3.8+
- pip
- virtualenv or venv

## Setup

1. Clone the repo:

	```bash
    git clone <repo-url>
    ```

2. Change into the project directory:

	```bash
    cd django-learning
    ```

3. Create and activate a virtual environment:

	```bash
    python -m venv .venv
    ```
	### Windows
    Command Prompt:
	```cmd
    .venv\Scripts\activate
    ```
    PowerShell:
    ```ps
    .venv\Scripts\Activate.ps1
    ```
	### macOS / Linux
	```bash
    source .venv/bin/activate
    ```

4. Install dependencies:

	```bash
    pip install -r requirements.txt
    ```

5. Apply migrations and create a superuser:

	```bash
    python manage.py migrate
    ```
	```bash
    python manage.py createsuperuser
    ```

6. Run the development server:

	```bash
    python manage.py runserver
    ```

## Project structure (typical)

- manage.py
- requirements.txt
- README.md
- <project_name>/
  - settings.py
  - urls.py
  - wsgi.py
- apps/
  - app1/

Adjust names to match this repository.

## Running tests

	 python manage.py test

## Notes

- Keep sensitive settings out of version control; use environment variables or a .env file.
- For deployment, configure allowed hosts, static files, and a production-ready database/server.

## License

This project is provided under the MIT License unless otherwise specified.
