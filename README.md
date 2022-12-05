# video-capture-for-tiscam
The Imaging Source社製USBカメラ用のVideoCapture。  
参考:  https://github.com/TheImagingSource/IC-Imaging-Control-Samples/tree/master/Python/tisgrabber

# 必要条件
opencv-python

# インストール方法
```
pip install git+https://github.com/a-nemoto313/video-capture-for-tiscam.git 
```

# クイックスタート
```python
import cv2

from my_video_capture.my_video_capture import MyVideoCapture

cap = MyVideoCapture(config_file_path="camera_config.xml")

while True:
    _, frame = cap.read()

    cv2.imshow("cam", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
```

# LICENSE
Copyright (C) 2022, サイトー株式会社, all rights reserved.

# INCLUDED
https://github.com/TheImagingSource/IC-Imaging-Control-Samples/tree/master/Python/tisgrabber/samples  
tisgrabber.py  
tisgrabber_x64.dll  
TIS_UDSHL11_x64.dll  
