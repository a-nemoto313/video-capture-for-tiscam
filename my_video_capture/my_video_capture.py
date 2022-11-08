import ctypes
import os

import cv2
import numpy as np

from my_video_capture import tisgrabber as tis


class MyVideoCapture:
    def __init__(self, dll_path="./tisgrabber_x64.dll", config_file_path=""):
        """
        argoカメラクラス。単体カメラを表示するクラス

        Args:
            dll_path (str): tisgrabbe_x64.dllの場所

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

        self._grabber = None
        self._get_device()  # カメラの接続を確認
        self.load_properties(config_file_path)  # 設定を読み込む

        # 取得した画像をそのままnumpy配列に変換するとなぜか上下反転するので、反転させるフィルターを有効化しておく
        self._filter = tis.HFRAMEFILTER()
        self.ic.IC_CreateFrameFilter(tis.T("Rotate Flip"), self._filter)

        self._start()
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

    def load_properties(self, config_file_path):
        """
        設定ファイルのロード。上手く読み込めなかったらエラーメッセージ

        Args:
            config_file_path (str):***.xml 読み込むファイルの場所

        """
        if os.path.exists(config_file_path):  # 設定ファイルが存在する場合➔設定を読み込み、カメラを起動
            self._grabber = self.ic.IC_LoadDeviceStateFromFile(None, tis.T(config_file_path))
        else:  # 設定ファイルが存在しない場合➔カメラは起動するが、設定を読み込めなかったメッセージを表示
            self._grabber = self.ic.IC_CreateGrabber()
            unique_name = self.ic.IC_GetUniqueNamefromList(0)
            self.ic.IC_OpenDevByUniqueName(self._grabber, unique_name)  # カメラ接続
            self.ic.IC_MsgBox(tis.T("Can not load config"), tis.T("Error"))  # エラーウィンドウが表示される

    def show_property_dialog(self):
        """
        設定変更ウィンドウを表示

        """
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

    def _get_device(self):
        """カメラが接続されているか確認する"""
        device_count = self.ic.IC_GetDeviceCount()  # 接続しているカメラ台数取得
        if device_count == 0:  # カメラの接続が無い場合
            self.ic.IC_MsgBox(tis.T("No device was found"), tis.T("Error"))  # エラーウィンドウが表示される
            raise ConnectionError("No device found.")

    def _start(self, create_window=False):
        """
        画像の取得の開始

        Args:
            create_window (bool): Trueだと、tisgrabberがウィンドウを生成してくれる

        """
        # 取得した画像をnumpy配列に変換するとなぜか上下反転されてるので、反転フィルターを事前に加える
        self.ic.IC_AddFrameFilterToDevice(self._grabber, self._filter)
        self.ic.IC_FrameFilterSetParameterBoolean(self._filter, tis.T("Flip V"), 1)

        self.ic.IC_StartLive(self._grabber, create_window)

    def _get_image_description(self):
        """取得する画像の情報を設定"""
        self.ic.IC_GetImageDescription(self._grabber,
                                       self._width, self._height, self._bits_per_pixel, self._color_format)

        self._channel = int(self._bits_per_pixel.value / 8.0)
        self._buffer_size = self._width.value * self._height.value * self._bits_per_pixel.value


if __name__ == '__main__':
    tisgrabber = "./tisgrabber_x64.dll"
    config_file = ""

    cap = MyVideoCapture(tisgrabber, config_file)

    cv2.namedWindow("img", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("img", 1200, 900)
    while True:
        ret_, img = cap.read()
        if not ret_:
            print("Camera is disconnected.")
            break

        cv2.imshow("img", img)
        k = cv2.waitKey(1)
        if k == 27:
            break
        elif k == ord("s"):
            cap.save_properties(config_file)
        elif k == ord("a"):
            cap.show_property_dialog()

    cv2.destroyAllWindows()
    cap.release()
