import zipfile
import os
import shutil
import random
import string
from pathlib import Path
import yaml
from collections import OrderedDict

from dotenv import load_dotenv
from cookiecutter.main import cookiecutter
from cookiecutter.exceptions import RepositoryNotFound
from flask import Flask, flash, request, redirect, url_for, render_template
from werkzeug.utils import secure_filename


# Configuration.
load_dotenv()
FILESIZE_LIMIT_UNCOMPRESSED = 25 # Mb
FILESIZE_LIMIT_COMPRESSED = 100 # Mb

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = FILESIZE_LIMIT_UNCOMPRESSED * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')

@app.route('/')
def home():
    """Form to post Rubric zip files."""
    return render_template('index.html')

def load_values(path):
    def ordered_load(stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
        class OrderedLoader(Loader):
            pass

        def construct_mapping(loader, node):
            loader.flatten_mapping(node)
            return object_pairs_hook(loader.construct_pairs(node))
        OrderedLoader.add_constructor(
	    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
	    construct_mapping)
        return yaml.load(stream, OrderedLoader)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'zip'

def uncompressed_filesize_ok(zipfile):
    return sum(e.file_size for e in zipfile.infolist()) > FILESIZE_LIMIT_UNCOMPRESSED

def contains_nested_zip(zipfile):
    return any(Path(f).suffix == '.zip' for f in zipfile.namelist())

@app.route('/upload-zip', methods=['POST'])
def upload_zip():
    """Upload a zip file (execute a user's uploaded Rubric and values)."""

    if 'file' not in request.files:
        flash('No file received')
        return redirect('/')
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect('/')
    if file and allowed_file(file.filename):

        # Set up file paths.
        filename = secure_filename(file.filename)
        rand_dir = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        root_dir = os.path.join(app.config['UPLOAD_FOLDER'], rand_dir)
        save_location = os.path.join(root_dir, filename)
        extract_path = os.path.join(root_dir, 'extracted')
        generated_path = os.path.join(root_dir, 'generated')
        values_path = os.path.join(extract_path, 'values.yml')

        # Save.
        os.mkdir(root_dir)
        file.save(save_location)

        # Unzip.
        with zipfile.ZipFile(save_location, 'r') as zip_ref:
            if not uncompressed_filesize_ok(zip_ref):
                flash('Uncompressed filesize too large')
                return redirect('/')
            if contains_nested_zip(zip_ref):
                flash('Zip file cannot contain another zip file')
                return redirect('/')
            else:
                zip_ref.extractall(extract_path)

        # Run cookiecutter.
        try:
            print(extract_path)
            print(values_path)
            print(load_values(values_path))
            print(generated_path)
            cookiecutter(extract_path, no_input=True, output_dir=generated_path, extra_context=load_values(values_path))
        except RepositoryNotFound as e:
            flash('Not a valid Rubric template (no rubric.yml in the top level of the zip at ' + extract_path + ' or values.yaml missing')
            return redirect('/')

        # Zip up.

        # Clean up.
        #shutil.rmtree(root_dir)

        # Return.
        return 'All done!'

app.run(debug=True)
