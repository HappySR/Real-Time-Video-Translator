# Getting Started with Your Application

### Clone the repository and navigate to the backend folder

```bash
git clone https://github.com/HappySR/rtvat-og.git
cd backend
```

To start testing your application after implementing the code, follow these steps:

## 1. Set Up Your Environment:

* **Python Dependencies:** Ensure you have Python installed along with Flask and other dependencies listed in `requirements.txt`.
* **FFmpeg:** Install FFmpeg on your machine. You can download it from the official FFmpeg website or use a package manager.

## 2. Create a Virtual Environment (optional but recommended):

```bash
python -m venv env
source env/bin/activate  # On Windows use 'env\Scripts\activate'
pip install -r requirements.txt
```

If you are facing some error in the whisper package, probably you have installed some other whisper, to install the openai-whisper run the following command:

```bash
pip install --upgrade openai-whisper
```

Then run the following command:

```bash
pip install -r requirements.txt
```

Once the depndencies are successfully configured, run the following command to list the current dependencies of your environment:

```bash
pip freeze > requirements.txt
```

Now you are ready to go to the next step!

## 3. Run Your Flask Backend:

```bash
python app.py
```
This will start your Flask server on http://127.0.0.1:5000.