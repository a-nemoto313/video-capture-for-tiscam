import ctypes
import os

import numpy as np

import my_video_capture.tisgrabber as tis


class MyVideoCapture:
    def __init__(self, config_file_path="", dll_path="./tisgrabber_x64.dll"):
        """
        argoカメラクラス。単体カメラを表示するクラス
        Args:
            dll_path (str): tisgrabber_x64.dllの場所
        """
        # 作業ディレクトリを一時的に移動
        main_dir = os.path.dirname(os.path.abspath("__main__"))
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        self.ic = ctypes.cdll.LoadLibrary(dll_path)
        os.chdir(main_dir)

        tis.declareFunctions(self.ic)

        self.ic.IC_InitLibrary(0)

        self._width = ctypes.c_long()           # 画像の幅
        self._height = ctypes.c_long()          # 画像の高さ
        self._bits_per_pixel = ctypes.c_int()   # ビット深度
        self._color_format = ctypes.c_int()     # カラーフォーマット
        self._channel = 0                       # チャンネル数
        self._buffer_size = 0                   # バッファサイズ

        self._grabber = self.ic.IC_CreateGrabber()
        self._apply_frame_filter()
        self._get_device()  # カメラの接続を確認

        self.load_properties(config_file_path, should_open_device=True)  # 設定を読み込む

        self._get_image_description()

    def read(self):
        """
        画像の取得
        Returns:
            (bool, img or None): (画像を取得できたかどうか, 3ch画像)
        """
        if self.ic.IC_SnapImage(self._grabber, -1) == tis.IC_SUCCESS:
            image_ptr = self.ic.IC_GetImagePtr(self._grabber)
            if image_ptr is not None:
                image_data = ctypes.cast(image_ptr, ctypes.POINTER(ctypes.c_ubyte * self._buffer_size))
                img_array = np.ndarray(buffer=image_data.contents, dtype=np.uint8,
                                       shape=(self._height.value, self._width.value, self._channel))
                return True, img_array
            else:
                raise ConnectionError("No device found.")
        else:
            return False, None

    def release(self):
        """終了処理"""
        if self.ic.IC_IsDevValid(self._grabber):
            self.ic.IC_StopLive(self._grabber)
            self.ic.IC_ReleaseGrabber(self._grabber)

    def save_properties(self, file_path):
        """
        設定ファイルの保存。XML形式。
        Args:
            file_path (str): ***.xml 保存する場所
        """
        self.ic.IC_SaveDeviceStateToFile(self._grabber, tis.T(file_path))

    def load_properties(self, config_file_path, should_open_device=False):
        """
        設定ファイルのロード。上手く読み込めなかったらエラーメッセージ
        設定ファイルを切り替える際もこの関数を使用する
        Args:
            config_file_path (str):***.xml 読み込むファイルの場所
            should_open_device (bool): OpenDeviceが 1 or 0
        """
        # ライブ中でも別の設定ファイルを読み込むことはできるが、設定を変更した直後にフレームを取得すると、
        # 変更が適用される前の画像が取得されることがある。そこで、一度ライブを止めてから設定を変更、再開することで回避できる。
        self.ic.IC_StopLive(self._grabber)

        ret = self.ic.IC_LoadDeviceStateFromFileEx(self._grabber, tis.T(config_file_path), should_open_device)
        # 設定ファイルが存在しない場合、デバイスがない場合、xmlの形式が間違っている場合
        if ret == tis.IC_FILE_NOT_FOUND or ret == tis.IC_DEVICE_NOT_FOUND or ret == tis.IC_WRONG_XML_FORMAT or \
                ret == tis.IC_WRONG_INCOMPATIBLE_XML:
            self.ic.IC_MsgBox(tis.T("Can not load config"), tis.T("Error"))  # エラーウィンドウが表示される
            if not self.ic.IC_IsDevValid(self._grabber):  # 設定ファイルが存在しない場合にカメラを開く
                unique_name = self.ic.IC_GetUniqueNamefromList(0)
                self.ic.IC_OpenDevByUniqueName(self._grabber, unique_name)  # カメラ接続

        self._start()

    def show_property_dialog(self):
        """設定変更ウィンドウを表示"""
        self.ic.IC_ShowPropertyDialog(self._grabber)

    def list_available_properties(self):
        """設定可能な項目一覧を表示。なぜかライブ中だと表示できない。"""
        self.ic.IC_printItemandElementNames(self._grabber)

    @property
    def width(self):
        """画像の幅"""
        return self._width.value

    @property
    def height(self):
        """画像の高さ"""
        return self._height.value

    def _apply_frame_filter(self):
        """
        取得する画像にフィルターを適用。
        いくつかあるが、90度回転、上下左右反転できるRotate Flipフィルターのみ使ってる
        https://www.theimagingsource.com/en-us/documentation/icimagingcontrolcpp/ref_stdfilter.htm
        """
        frame_filter = tis.HFRAMEFILTER()
        self.ic.IC_CreateFrameFilter(tis.T("Rotate Flip"), frame_filter)
        self.ic.IC_AddFrameFilterToDevice(self._grabber, frame_filter)
        # なぜか画像が上下反転してしまうので、反転フィルターで元に戻す。
        self.ic.IC_FrameFilterSetParameterBoolean(frame_filter, tis.T("Flip V"), 1)

    def _start(self, create_window=False):
        """
        画像の取得の開始
        Args:
            create_window (bool): Trueだと、tisgrabberがウィンドウを生成してくれる
        """
        self.ic.IC_StartLive(self._grabber, create_window)

    def _get_device(self):
        """カメラが接続されているか確認する"""
        device_count = self.ic.IC_GetDeviceCount()  # 接続しているカメラ台数取得
        if device_count == 0:  # カメラの接続が無い場合
            self.ic.IC_MsgBox(tis.T("No device was found"), tis.T("Error"))  # エラーウィンドウが表示される
            raise ConnectionError("No device found.")

    def _get_image_description(self):
        """取得する画像の情報を設定"""
        self.ic.IC_GetImageDescription(self._grabber,
                                       self._width, self._height, self._bits_per_pixel, self._color_format)

        self._channel = int(self._bits_per_pixel.value / 8.0)
        self._buffer_size = self._width.value * self._height.value * self._bits_per_pixel.value


if __name__ == '__main__':
    import cv2

    config_file1 = ""
    config_file2 = ""

    cap = MyVideoCapture(config_file1)

    window_width = 1200
    window_height = 900
    cv2.namedWindow("img", cv2.WINDOW_NORMAL)
    cv2.namedWindow("config 1", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("config 1", window_width, window_height)
    cv2.namedWindow("config 2", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("config 2", window_width, window_height)
    while True:
        ret_, img = cap.read()
        if not ret_:
            print("Camera is disconnected.")
            break

        cv2.imshow("img", img)
        k = cv2.waitKey(1)
        if k == 27:
            break

        elif k == ord("1"):  # 設定ファイルが切り替わる
            cap.load_properties(config_file1)
            # ちゃんと設定変更後の画像が取得できているか確認。特に露光。
            _, frame = cap.read()
            cv2.imshow("config 1", frame)
        elif k == ord("2"):  # 設定ファイルが切り替わる
            cap.load_properties(config_file2)
            # ちゃんと設定変更後の画像が取得できているか確認。特に露光。
            _, frame = cap.read()
            cv2.imshow("config 2", frame)

        elif k == ord("s"):
            cap.save_properties(config_file1)
        elif k == ord("a"):
            cap.show_property_dialog()

    cv2.destroyAllWindows()
    cap.release()
