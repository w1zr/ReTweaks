"""Local daily-tool operations. Originals are never modified."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import quote,unquote
from PIL import Image,ImageOps
from branding import ASSETS

FORMATS={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp','BMP':'.bmp','ICO':'.ico'}

def bounds_from(width,height):
    try:w=int(width or 0);h=int(height or 0)
    except ValueError:raise ValueError('Width and height must be whole numbers.')
    if w<0 or h<0 or w>16000 or h>16000:raise ValueError('Dimensions must be between 0 and 16000 pixels. Use 0 to keep that dimension unrestricted.')
    return w,h

def opaque(image):
    rgba=image.convert('RGBA');result=Image.new('RGB',rgba.size,'white');result.paste(rgba,mask=rgba.getchannel('A'));return result

def save_new(folder,stem,suffix,writer):
    folder=Path(folder)
    if not folder.is_dir():raise ValueError('Choose an existing output folder.')
    for number in range(1,10001):
        path=folder/(stem+('' if number==1 else '_'+str(number))+suffix)
        try:stream=path.open('xb')
        except FileExistsError:continue
        try:
            with stream:writer(stream)
        except BaseException:
            path.unlink(missing_ok=True);raise
        return path
    raise ValueError('Too many files with that name. Choose another output folder.')

def convert_image(source,folder,format='PNG',bounds=(0,0)):
    if format not in FORMATS:raise ValueError('Unsupported output format.')
    w,h=bounds_from(*bounds)
    with Image.open(source) as original:
        image=ImageOps.exif_transpose(original).copy()
    image.thumbnail((w or image.width,h or image.height),Image.Resampling.LANCZOS)
    if format in ('JPEG','BMP'):image=opaque(image)
    elif format in ('PNG','WEBP','ICO'):image=image.convert('RGBA')
    if format=='ICO':
        image.thumbnail((256,256),Image.Resampling.LANCZOS)
        edge=max(image.size);square=Image.new('RGBA',(edge,edge));square.alpha_composite(image,((edge-image.width)//2,(edge-image.height)//2));image=square
    # Export only pixels, not source EXIF/GPS metadata.
    clean=Image.new(image.mode,image.size);clean.paste(image)
    options={'quality':92} if format in ('JPEG','WEBP') else {}
    if format=='ICO':options['sizes']=[(edge,edge) for edge in (16,32,48,64,128,256) if edge<image.width]+[image.size]
    return save_new(folder,Path(source).stem+'_converted',FORMATS[format],lambda stream:clean.save(stream,format=format,**options))

def images_to_pdf(paths,folder):
    if not paths or len(paths)>50:raise ValueError('Choose between 1 and 50 images for one PDF.')
    pages=[];pixels=0
    try:
        for path in paths:
            with Image.open(path) as original:
                image=ImageOps.exif_transpose(original);image.thumbnail((2400,2400),Image.Resampling.LANCZOS);page=opaque(image)
            pixels+=page.width*page.height
            if pixels>80000000:page.close();raise ValueError('This PDF is too large. Split it into smaller groups of images.')
            pages.append(page)
        return save_new(folder,'RETWEAKS_images','.pdf',lambda stream:pages[0].save(stream,format='PDF',save_all=True,append_images=pages[1:],resolution=150))
    finally:
        for page in pages:page.close()

def sha256_file(path):
    digest=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def transform_text(text,action):
    if action=='Trim lines':return '\n'.join(line.strip() for line in text.splitlines())
    if action=='Remove blank lines':return '\n'.join(line for line in text.splitlines() if line.strip())
    if action=='Remove duplicate lines':return '\n'.join(dict.fromkeys(text.splitlines()))
    if action=='Sort lines':return '\n'.join(sorted(text.splitlines(),key=str.casefold))
    if action=='UPPERCASE':return text.upper()
    if action=='lowercase':return text.lower()
    if action=='Format JSON':return json.dumps(json.loads(text),ensure_ascii=False,indent=2)
    if action=='URL encode':return quote(text,safe='')
    if action=='URL decode':return unquote(text)
    if action=='Base64 encode':return base64.b64encode(text.encode('utf-8')).decode('ascii')
    if action=='Base64 decode':return base64.b64decode(text,validate=True).decode('utf-8')
    raise ValueError('Choose a text operation.')

TEXT_ACTIONS=['Trim lines','Remove blank lines','Remove duplicate lines','Sort lines','UPPERCASE','lowercase','Format JSON','URL encode','URL decode','Base64 encode','Base64 decode']

# Windows OCR API: https://learn.microsoft.com/uwp/api/windows.media.ocr.ocrengine
def extract_text(source):
    with tempfile.TemporaryDirectory(prefix='RETWEAKS-OCR-') as folder:
        path=Path(folder)/'image.png'
        with (source.copy() if isinstance(source,Image.Image) else Image.open(source)) as original:
            image=opaque(ImageOps.exif_transpose(original));image.thumbnail((2500,2500),Image.Resampling.LANCZOS);image.save(path)
        powershell=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        result=subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(ASSETS/'windows_ocr.ps1'),'-ImagePath',str(path)],capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:record=json.loads(result.stdout.decode('utf-8-sig').strip())
        except (ValueError,UnicodeError):raise RuntimeError('Windows text recognition could not start. Check that Windows OCR language support is installed.')
        if result.returncode or record.get('error'):raise RuntimeError(record.get('error','Windows text recognition failed.'))
        return record
