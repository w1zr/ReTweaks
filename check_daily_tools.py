"""Daily tools checks use generated files; no personal files or Windows settings change."""
import hashlib,json,tempfile,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from pypdf import PdfReader
import daily_toolkit as tools

tempfile.tempdir=str((Path(__file__).resolve().parent/'verification').resolve())
with tempfile.TemporaryDirectory(prefix='RETWEAKS-tools-check-') as folder:
    assert Path(folder).resolve().is_relative_to(Path(tempfile.tempdir))
    root=Path(folder);source=root/'source.png';image=Image.new('RGBA',(600,300),(255,0,0,0));image.putpixel((0,0),(10,20,30,255));image.save(source)
    before=source.read_bytes()
    for format,suffix in tools.FORMATS.items():
        path=tools.convert_image(source,root,format,(200,200))
        with Image.open(path) as output:
            assert output.size==((200,200) if format=='ICO' else (200,100)),(format,output.size)
            if format in ('JPEG','BMP'):assert all(c>240 for c in output.convert('RGB').getpixel((150,70)))
    next_path=tools.convert_image(source,root,'PNG',(200,0));assert next_path.name=='source_converted_2.png'
    assert source.read_bytes()==before
    assert tools.bounds_from('0','200')==(0,200)
    for bounds in [('-1','3'),('no','3'),('17000','3')]:
        try:tools.bounds_from(*bounds);raise AssertionError('Invalid dimensions accepted')
        except ValueError:pass
    # Rotation metadata is applied before resizing, and not copied to exports.
    photo=root/'rotated.jpg';rot=Image.new('RGB',(300,100),'blue');exif=Image.Exif();exif[274]=6;rot.save(photo,exif=exif)
    path=tools.convert_image(photo,root,'PNG')
    with Image.open(path) as output:assert output.size==(100,300) and not output.getexif()
    pdf=tools.images_to_pdf([source,photo],root);reader=PdfReader(pdf);assert len(reader.pages)==2
    assert tools.sha256_file(source)==hashlib.sha256(before).hexdigest()
    assert tools.transform_text(' a \n\nb\na','Trim lines')=='a\n\nb\na'
    assert tools.transform_text('a\na\nb','Remove duplicate lines')=='a\nb'
    assert tools.transform_text('a\n \nb','Remove blank lines')=='a\nb'
    assert tools.transform_text('b\na','Sort lines')=='a\nb'
    text='Hello, café!'
    assert tools.transform_text(tools.transform_text(text,'Base64 encode'),'Base64 decode')==text
    assert tools.transform_text(tools.transform_text(text,'URL encode'),'URL decode')==text
    assert json.loads(tools.transform_text('{"a":1}','Format JSON'))=={'a':1}
    try:tools.transform_text('{','Format JSON');raise AssertionError('Invalid JSON accepted')
    except ValueError:pass
    try:tools.save_new(root,'broken','.tmp',lambda stream:(_ for _ in ()).throw(ValueError('failed')))
    except ValueError:assert not (root/'broken.tmp').exists()
    if '--ocr' in sys.argv:
        sample=root/'ocr.png';im=Image.new('RGB',(1200,240),'white');ImageDraw.Draw(im).text((30,60),'RETWEAKS daily tools 123',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',64),fill='black');im.save(sample)
        for source in [sample,im]:
            result=tools.extract_text(source);assert 'daily tools 123' in result['text'],result
        print('PASS: real local Windows OCR from a generated file and clipboard-style image.')
print('PASS: all 5 image formats, proportions, alpha flattening, rotation, metadata removal, collision-safe output, unchanged originals, PDF pages, hashing, text transforms and partial-output cleanup.')
