from setuptools import setup

setup(
    name="MyVideoCapture",
    version="1.0.3",
    description="read camera",
    url="https://github.com/a-nemoto313/video-capture-for-tiscam",
    packages=["my_video_capture"],
    data_files=[("./Lib/site-packages/my_video_capture", ["./my_video_capture/TIS_UDSHL11_x64.dll"]),
                ("./Lib/site-packages/my_video_capture", ["./my_video_capture/tisgrabber_x64.dll"])],
    include_package_data=True,
)
