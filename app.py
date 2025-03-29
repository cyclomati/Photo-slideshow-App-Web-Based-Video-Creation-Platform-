from flask import Flask, flash, render_template, request, redirect, url_for, session
from flask_bcrypt import Bcrypt
import jwt
import mysql.connector
import cv2 
import numpy as np
import base64
from PIL import Image
import io 
from io import BytesIO
import os
from moviepy.editor import VideoClip, concatenate_videoclips, AudioFileClip, ImageSequenceClip,concatenate_audioclips

import matplotlib.pyplot as plt
from flask import send_file
import requests
import tempfile

import psycopg2
import psycopg2.extras




app = Flask(__name__)
app.secret_key = 'your_secret_key' 
bcrypt = Bcrypt(app)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = psycopg2.connect(
   host="touchy-merman-1-8984.8nk.gcp-asia-southeast1.cockroachlabs.cloud",
   port="26257",
   user="phase3",
   password="xV5JK_clQMyOMZ6tIEsWpg",
   dbname="project3",
   sslmode="verify-full",
   sslrootcert="root.crt"
   
)
cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

def calculate_average_size(image_filenames):
    total_width = 0
    total_height = 0
    num_images = len(image_filenames)

    for filename in image_filenames:
        image = cv2.imread(filename)
        height, width, _ = image.shape
        total_width += width
        total_height += height

    average_width = total_width // num_images
    average_height = total_height // num_images

    return average_width, average_height

def resize_image(image, width, height):
    return cv2.resize(image, (width, height))

def convert_data(data, file_name):
    with open(file_name, 'wb') as file:
        file.write(data)

JWT_SECRET_KEY = 'your_jwt_secret_key'

@app.route('/')
def default():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if 'signup' in request.form:
            name = request.form['name']
            username = request.form['username']
            password = request.form['password']
            email = request.form['email']
            
            password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

            
            cursor.execute("INSERT INTO public.users (name, username, useremail, userpassword) VALUES (%s, %s, %s, %s)",
                           (name, username, email, password_hash))
            db.commit()

            return redirect(url_for('login'))
        else:
            username = request.form['username']
            password = request.form['password']
            
            if username == 'admin' and password == 'admin145':
                cursor.execute("SELECT userid, name, username, useremail FROM public.users")
                users = cursor.fetchall()
                return render_template('admin.html', users=users)
            else:
                cursor.execute("SELECT * FROM public.users WHERE username = %s", (username,))
                user = cursor.fetchone()

                if user and bcrypt.check_password_hash(user['userpassword'], password):
                    token = jwt.encode({'user_id': user['userid'], 'username': user['username']}, JWT_SECRET_KEY, algorithm='HS256')
                    session['token'] = token
                    return redirect(url_for('home'))
                else:
                    error = 'Invalid username or password'
                    return render_template('login.html', error=error)
                
    if 'token' in session:
        try:
            decoded_token = jwt.decode(session['token'], JWT_SECRET_KEY, algorithms=['HS256'])
            user_id = decoded_token['user_id']
            return redirect(url_for('home'))
        except jwt.ExpiredSignatureError:
            pass  
        except jwt.InvalidTokenError:
            pass  
                
    return render_template('login.html')


@app.route('/home')
def home():
    token = session.get('token')
    if token:
        try:
            decoded_token = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
            user_id = decoded_token['user_id']
            
            cursor.execute("SELECT image, image_metadata FROM public.images WHERE userid = %s", (user_id,))
            image_data = cursor.fetchall() 
                       
            images_base64 = []
            metadata = []
            
            for data in image_data:
                fdata = data
                img_data = base64.b64encode(data['image']).decode('utf-8')
               
                image = img_data
                
                if image is not None:  
                   
                    img_base64 = image
                    images_base64.append(img_base64)
                    metadata.append(data['image_metadata'])

                    filename = data['image_metadata']
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    with open(file_path, 'wb') as f:
                        f.write(fdata['image'])
                else:
                    print("Failed to decode this image:")
                    
            images_with_metadata = list(zip(images_base64, metadata))
            
            cursor.execute("SELECT * FROM public.users WHERE userid = %s", (user_id,))
            user = cursor.fetchone()
           
            cursor.execute("SELECT audio, audio_metadata FROM public.audios WHERE userid = %s", (user_id,))
            audio_data = cursor.fetchall()
            audio_base64_list = []
            for audio_entry in audio_data:
                    fdata = audio_entry
                    audio_base64 = base64.b64encode(audio_entry['audio']).decode('utf-8')
                    audio_base64_list.append((audio_base64, audio_entry['audio_metadata']))
                    filename = fdata['audio_metadata']
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    with open(file_path, 'wb') as f:
                        f.write(fdata['audio'])                    
                    
            if user:
                return render_template('home.html',audio_base64_list=audio_base64_list, images_with_metadata=images_with_metadata, user=user, user_id=user_id, username=user['username'],name=user['name'],useremail=user['useremail'])
            else:
                return redirect(url_for('login'))
        except jwt.ExpiredSignatureError:
            return redirect(url_for('login'))
    else:
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
         file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
         os.remove(file_path)
    session.pop('token', None)
    return redirect(url_for('login'))

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        token = session.get('token')
        if not token:
            return redirect(url_for('login'))
        
        decoded_token = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        user_id = decoded_token['user_id']

        if 'image' not in request.files:
            return redirect(request.url)
        
        files = request.files.getlist('image')

        for file in files:
            if file:
                filename = file.filename
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                with open(file_path, 'rb') as f:
                   image_data = f.read()
                  
                   cur = db.cursor()
                   cur.execute("INSERT INTO public.images (userid, image, image_metadata) VALUES (%s, %s, %s)", (user_id, image_data, filename))
                   db.commit()
                   cur.close()
                os.remove(file_path)   
                
        return redirect(url_for('upload'))
    
    return render_template('upload.html')  

@app.route('/create' , methods=['GET', 'POST'])
def create():
    token = session.get('token')
    if token:
        try:
            decoded_token = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
            user_id = decoded_token['user_id']

            cursor.execute("SELECT image, image_metadata FROM public.images WHERE userid = %s", (user_id,))
            image_data = cursor.fetchall() 
                       
            images_base64 = []
            metadata = []
            
            for data in image_data:
                fdata = data
                img_data = base64.b64encode(data['image']).decode('utf-8')
               
                image = img_data
                
                if image is not None:  
                   
                    img_base64 = image
                    images_base64.append(img_base64)
                    metadata.append(data['image_metadata'])

                    filename = data['image_metadata']
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    with open(file_path, 'wb') as f:
                        f.write(fdata['image'])
                else:
                    print("Failed to decode this image:")
                    
            images_with_metadata = list(zip(images_base64, metadata))
            
            cursor.execute("SELECT * FROM public.users WHERE userid = %s", (user_id,))
            user = cursor.fetchone()
           
            cursor.execute("SELECT audio, audio_metadata FROM public.audios WHERE userid = %s", (user_id,))
            audio_data = cursor.fetchall()
            audio_base64_list = []
            for audio_entry in audio_data:
                    
                    fdata = audio_entry
                    audio_base64 = base64.b64encode(audio_entry['audio']).decode('utf-8')
                    audio_base64_list.append((audio_base64, audio_entry['audio_metadata']))
                    filename = fdata['audio_metadata']
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    with open(file_path, 'wb') as f:
                        f.write(fdata['audio'])
                    

            if request.method == 'POST':
                
              image_filenames = []
  
              selected_images_metadata = request.form.getlist('metadata')
              selected_images_metadata = (selected_images_metadata[0])

              if selected_images_metadata:
                metadata_list = selected_images_metadata.split(',')
              
              for metadata in metadata_list:
           
                
                image_filename = os.path.join(app.config['UPLOAD_FOLDER'], metadata.strip())  
            
            
                if os.path.exists(image_filename):
                  image_filenames.append(image_filename)  


              audio_filenames = []
  
              selected_audio_metadata = request.form.getlist('audio_metadata')

              selected_audio_metadata = (selected_audio_metadata[0])

              if selected_audio_metadata:
                audio_metadata_list = selected_audio_metadata.split(',')
              
                for metadata1 in audio_metadata_list:
           
                
                  audio_filename = os.path.join(app.config['UPLOAD_FOLDER'], metadata1.strip())  
            
            
                  if os.path.exists(audio_filename):
                    audio_filenames.append(audio_filename)                   
                  
                  
                
              if image_filenames:
                 
                 if(len(image_filenames)==1) : 
                  x =680
                  y=480
                  image_filenames.append(image_filenames[0])
                  duration_per_image = (float(request.form['duration_per_image']))/2
                  
                 else:
                     average_width, average_height = calculate_average_size(image_filenames)
                     x =680
                     y=480
                     duration_per_image = float(request.form['duration_per_image'])
                     
                 images = [resize_image(cv2.imread(image), x, y) for image in image_filenames]
                 imgz = images
                
                 fps = 1 / duration_per_image
                 video_clip = ImageSequenceClip(images, fps=fps)
                 vclip = ImageSequenceClip(imgz,fps=fps)
                 if audio_filenames:
                    audio_clips = [AudioFileClip(audio_filename) for audio_filename in audio_filenames]
                    final_audio_clip = concatenate_audioclips(audio_clips * len(images))
                    final_audio_duration = len(images) * duration_per_image
                    if audio_clips:
                       total_audio_duration = sum([clip.duration for clip in audio_clips])
                      

       
                   
                       if final_audio_duration > total_audio_duration:
                         message = "Warning: The duration of the video exceeds the duration of the audio."
                         return redirect(url_for('create', message=message))
                          
                    final_audio_clip = final_audio_clip.set_duration(final_audio_duration)

                    video_clip = video_clip.set_audio(final_audio_clip)
                    vclip = vclip.set_audio(final_audio_clip)
            
                 with tempfile.NamedTemporaryFile(suffix='.mp4') as temp_file:
                
                   video_clip.write_videofile(temp_file.name, codec='libx264', fps=fps, verbose=False)

                
                   temp_file.seek(0)
                   video_data = temp_file.read()
                
                 video_base64 = base64.b64encode(video_data).decode('utf-8')
                 
                 permanent_video_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output_video.mp4') 
                 vclip.write_videofile(permanent_video_path,codec='libx264', fps=fps, verbose=False)
                 
                   
                 return render_template('create.html', video_base64=video_base64, user=user, user_id=user_id, username=user['username'])  
            
                  
              return redirect(url_for('create'))  

    
            
            if user:
                return render_template('create.html',audio_base64_list=audio_base64_list,images_with_metadata= images_with_metadata, user=user, user_id=user_id, username=user['username'])
            else:
                return redirect(url_for('login'))
        except jwt.ExpiredSignatureError:
            return redirect(url_for('login'))
    else:
        return redirect(url_for('login'))

@app.route('/download-video')
def download_video():
     temp_video_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output_video.mp4')
     
     if os.path.exists(temp_video_path):
       response =  send_file(temp_video_path, as_attachment=True)

       
       
       return response
     else:
          return "Error: Video File not yet created. Return Back & create one"
          

@app.route('/upload_audio', methods=['GET', 'POST'])
def upload_audio_form():
    if request.method == 'POST':
        if 'audio' not in request.files:
            return "No file part"
        
        file = request.files['audio']
        if file.filename == '':
            return "No selected file"
        
        if file:
            filename = file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                
                token = session.get('token')
                decoded_token = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
                user_id = decoded_token['user_id']
                

                with open(filepath, 'rb') as f:
                    audio_data = f.read()
                
                
                cursor = db.cursor()
                cursor.execute("INSERT INTO public.audios (audio, audio_metadata, userid) VALUES (%s, %s, %s)", (audio_data, filename, user_id))
                db.commit()
                cursor.close()
                
               
                os.remove(filepath)
                
                
                return redirect(url_for('upload_audio_form'))
            except Exception as e:
               
                os.remove(filepath)
                return f"Error uploading file: {str(e)}"

    return render_template('upload_audio.html')

if __name__ == '__main__':
    app.run(debug=True)
