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
from flask import Flask, flash, request, redirect, url_for, render_template, send_file
from werkzeug.utils import secure_filename


# Configuration.
load_dotenv()
FILESIZE_LIMIT_UNCOMPRESSED = 25 # Mb
FILESIZE_LIMIT_COMPRESSED = 100 # Mb

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = FILESIZE_LIMIT_UNCOMPRESSED * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['CLEANUP'] = False

@app.route('/')
def home():
    """Form to post Rubric zip files."""
    return render_template('index.html')

def load_values(stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
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
        flash('Error: No file received', 'is-danger')
        return redirect('/')
    file = request.files['file']
    if not file or file.filename == '':
        flash('Error: No selected file', 'is-danger')
        return redirect('/')
    if not allowed_file(file.filename):
        flash('Error: Expected a zip file', 'is-danger')
        return redirect('/')

    if 42:
        # Set up file paths.
        filename = secure_filename(file.filename)
        rand_dir = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        root_dir = os.path.join(app.config['UPLOAD_FOLDER'], rand_dir)

        save_location = os.path.join(root_dir, 'uploaded', filename)

        extract_path = os.path.join(root_dir, 'extracted')
        generated_path = os.path.join(root_dir, 'generated')
        final_zip_path = os.path.join(root_dir, 'zipped', filename)

        # Save.
        os.mkdir(root_dir)
        os.mkdir(os.path.join(root_dir, 'uploaded'))
        os.mkdir(os.path.join(root_dir, 'zipped'))
        file.save(save_location)

        # Limitation checks.
        with zipfile.ZipFile(save_location, 'r') as zip_ref:
            if not uncompressed_filesize_ok(zip_ref):
                flash(f'Error: Uncompressed filesize >{FILESIZE_LIMIT_UNCOMPRESSED}Mb', 'is-danger')
                return redirect('/')
            if contains_nested_zip(zip_ref):
                flash('Error: Zip file cannot contain another zip file', 'is-danger')
                return redirect('/')

        # Unzip.
        shutil.unpack_archive(save_location, extract_path, 'zip')

        # Run cookiecutter.
        try:
            try:
                values_path = os.path.join(extract_path, 'values.yml')
                with open(values_path) as values_file_handle:
                    vals = load_values(values_file_handle, yaml.SafeLoader)
            except FileNotFoundError as e:
                flash('values.yml missing', 'is-danger')
                return redirect('/')
            cookiecutter(extract_path, no_input=True, output_dir=generated_path, extra_context=vals)
        except RepositoryNotFound as e:
            flash('Error: not a valid Rubric template - no rubric.yml in the top level of the zip', 'is-danger')
            return redirect('/')

        # Zip up.
        shutil.make_archive(final_zip_path[:-4], 'zip', generated_path)

        # Clean up.
        if app.config['CLEANUP']:
            shutil.rmtree(root_dir)

        # Return.
        newfilename = filename[:-4] + '-result.zip'
        return send_file(final_zip_path, as_attachment=True, attachment_filename=newfilename)

app.run(debug=True)
