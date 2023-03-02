import logging
import os
import flask
import typing
import shutil
import zipfile
from threading import Thread
import subprocess

import localization
from libs.utils.loader import *
from libs.utils.projection import *
from libs.utils.domain import *
import io
import tempfile

app = flask.Flask(__name__)
localizers: typing.Dict[int, localization.Localizer] = {}
intrinsics: typing.Dict[int, np.ndarray] = {}

def load_localizer(project_id: int) -> typing.Tuple[localization.Localizer]:
     
    home = os.environ.get('HOME')
    sample_data = os.path.join(f"{home}/datasets", f"project_{project_id}")
    if not os.path.exists(sample_data):
        return None
    l = LocalLoader(sample_data)
    loc = localization.Localizer(l)

    return loc

app.logger.info("API server ready")

@app.route("/api/v1/project/<int:project_id>/load")
def load_project(project_id):
    loc = load_localizer(project_id)
    if loc is None:
        return flask.make_response("Project not found", 404)
    localizers[project_id] = loc
    intrinsics[project_id] = loc.camera_matrix
    print(f'Loaded project {project_id}')    
    return flask.make_response("Project loaded successfully")

@app.route("/api/v1/project/<int:project_id>/intrinsics", methods=["POST"])
def add_intrinsics(project_id):
    if flask.request.method == "POST":
        if "camera_matrix" in flask.request.json:
            intrinsics[project_id] = np.array(flask.request.json["camera_matrix"])    
            return flask.make_response("Query camera intrinsics added successfully")  
        else:
            return flask.make_response("Query camera intrinsics not found", 404)
    else:
        return flask.make_response("Invalid request", 404)

@app.route("/api/v1/project/<int:project_id>/localize", methods=["POST"])
def localize_request(project_id):
    if project_id not in localizers:
        return flask.make_response("Project not loaded", 404)
    
    if flask.request.method == "POST":
        if flask.request.files.get("image"):
            loc = localizers[project_id]

            img = Image.open(io.BytesIO(flask.request.files["image"].read()))    
            img = np.array(img)

            camera_matrix = intrinsics[project_id]
            T_m1_c2, inliers = loc.callback_query(img, camera_matrix)
            if T_m1_c2 is None:
                res = {'success':False}
            else:
                pose = matrix2pose(T_m1_c2)
                res = {'pose':tuple(pose.tolist()), 'inliers':inliers, 'success':True}

            return flask.make_response(res)

        else:
            return flask.make_response("Image not found", 404)
    else:
        return flask.make_response("Invalid request", 404)


# post request method for uploading data to local filesystem for development
@app.route("/api/v1/project/<int:project_id>/upload", methods=["POST"])
def upload(project_id):
    if flask.request.method == "POST":
        if len(flask.request.data) > 0:

            with open(os.path.join("/Data.zip"), "wb") as f:
                f.write(flask.request.data)

            home = os.environ.get('HOME')
            sample_data = os.path.join(home, "datasets", f"project_{project_id}")
            os.makedirs(sample_data, exist_ok=True)

            thread = Thread(
                target=preprocess_task, args=(sample_data,project_id,)
            )
            thread.start()

            return "success"
        else:
            return flask.make_response("Data not found", 404)
    else:
        return flask.make_response("Invalid request", 404)

def preprocess_task(sample_data,project_id):
    print("started preprocessing...")
    shutil.rmtree(os.path.join("/Data"), ignore_errors=True)
    with zipfile.ZipFile("/Data.zip", "r") as zip_ref:
        zip_ref.extractall("/Data")
    shutil.rmtree(sample_data, ignore_errors=True)

    # remove output directory folders if they exist
    frame_rate = 2
    max_depth = 5
    voxel = 0.01
    # create preprocessor object
    home = os.environ.get('HOME')
    process = subprocess.Popen(["python3", "preprocessor/cli.py",
                                "-i", "/Data", "-o", sample_data, "-f", str(frame_rate), "-d", str(max_depth), "-v", str(voxel),
                                "--mobile_inspector"])
    process.wait()

    print('Reloading project...')  
    loc_1 = load_localizer(project_id) 
    loc_1.build_database()
    localizers[project_id] = loc_1
    intrinsics[project_id] = loc_1.camera_matrix     
    print(f'Loaded project {project_id}')    

if __name__ == "__main__":
    #app.run(host='0.0.0.0',port=5000)
    init_ip_address()
    app.run(host='::',port=5000, debug=True)    
