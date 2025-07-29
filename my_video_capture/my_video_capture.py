import os
import time
import ctypes
import logging
import threading
from typing import Callable

import cv2
import numpy as np

from . import tisgrabber as tis

# ライブラリのルートロガーを作成
logger = logging.getLogger('ic_camera_control')
logger.addHandler(logging.NullHandler())


def configure_logging(level=logging.WARNING, handler=None):
    """ ライブラリのロガー設定を行う関数

    Args:
        level (int): ログレベル (e.g., logging.DEBUG, logging.INFO, etc.)
        handler (logging.Handler): ログ出力先のハンドラー (省略時はStreamHandler)
    """
    if handler is None:
        handler = logging.StreamHandler()

    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(level)


class CallbackUserdata(ctypes.Structure):
    """  コールバック関数に渡されるユーザーデータの例 """

    def __init__(self, ):
        self.unsused = ""
        self.devicename = ""
        self.connected = False


class MyVideoCapture:
    def __init__(
        self,
        config_file_path: str = "",
        dll_path: str = "./tisgrabber_x64.dll",
        frame_ready_callback: "Callable[[ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p], None]" = None,
        device_lost_callback: "Callable[[ctypes.c_void_p, CallbackUserdata], None]" = None,
    ):
        """ 単体カメラを表示するクラス

        Args:
            dll_path (str): tisgrabber_x64.dllの場所
            config_file_path (str): カメラのコンフィグファイルの場所
            dll_path (str): tisgrabber_x64.dllの場所
            frame_ready_callback (Callable[[ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p], None], optional):
                画像フレームが準備できたときに呼ばれるコールバック関数。
                引数は (hGrabber, pBuffer, framenumber, pData)。
            device_lost_callback (Callable[[ctypes.c_void_p, CallbackUserdata], None], optional):
                デバイスが切断されたときに呼ばれるコールバック関数。
                引数は (hGrabber, userdata)。
        """
        self._width = ctypes.c_long()  # 画像の幅
        self._height = ctypes.c_long()  # 画像の高さ
        self._bits_per_pixel = ctypes.c_int()  # ビット深度
        self._color_format = ctypes.c_int()  # カラーフォーマット
        self._channel = 0  # チャンネル数
        self._buffer_size = 0  # バッファサイズ
        self._config_file_path = config_file_path
        self._hGrabber = None

        # tisgrabber_x64.dllをインポート
        main_dir = os.path.dirname(os.path.abspath("__main__"))
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        self.ic = ctypes.cdll.LoadLibrary(dll_path)
        os.chdir(main_dir)
        tis.declareFunctions(self.ic)

        self._grabber = self.ic.IC_CreateGrabber()

        self.load_properties(config_file_path, should_open_device=True)  # 設定を読み込む
        # ICImagingControlクラスライブラリを初期化
        self.ic.IC_InitLibrary(0)

        # 関数ポインタを作成
        if frame_ready_callback is None:
            frame_ready_callback = self._frameReadyCallback
        self.frameReadyCallbackFunc = self.ic.FRAMEREADYCALLBACK(frame_ready_callback)
        self.userdata = CallbackUserdata()
        if device_lost_callback is None:
            device_lost_callback = self._deviceLostCallback
        self.deviceLostCallbackFunc = self.ic.DEVICELOSTCALLBACK(device_lost_callback)

        # デバイスを開く
        self.open_device(self._config_file_path)

    @staticmethod
    def _frameReadyCallback(hGrabber, pBuffer, framenumber, pData):
        # コールバック関数処理
        # 省略
        return

    @staticmethod
    def _deviceLostCallback(hGrabber, userdata):
        """ このデバイスはコールバック関数を失いました。 カメラが切断された場合に呼び出されます。
        この関数は、メインスレッドではなく、別スレッドで実行されます。

        Args:
            hGrabber: これはグラバーオブジェクトへの実際のポインターです。（使用禁止）
            userdata: ユーザーデータ構造へのポインター
        """
        userdata.connected = False
        logger.error(f"Device {userdata.devicename} lost")

    @staticmethod
    def _handle_device_open_error():
        logger.info("No device opened")

    def read(self):
        """
        画像を取得する

        Returns:
            tuple: (bool, np.ndarray or None)
                画像取得に成功した場合は (True, 画像配列)、
                失敗した場合は (False, None) を返す
        """
        if self.ic.IC_SnapImage(self._hGrabber, 2000) == tis.IC_SUCCESS:
            image_ptr = self.ic.IC_GetImagePtr(self._hGrabber)
            if image_ptr is not None:
                image_data = ctypes.cast(image_ptr, ctypes.POINTER(ctypes.c_ubyte * self._buffer_size))
                img_array = np.ndarray(buffer=image_data.contents, dtype=np.uint8,
                                       shape=(self._height.value, self._width.value, self._channel))
                return True, img_array

        if self.userdata.connected is False:
            self.reconnect_wait()

        return False, None

    def open_device(self, config_file_path: str = None):
        """ デバイスを開く

        設定ファイルがある場合は、設定ファイルの情報を元に開く
        設定ファイルがなく2つ以上の接続がある場合はダイアログで選択する
        Args:
            config_file_path (str):***.xml 読み込むファイルの場所

        Returns:
            bool: 開くことができたか
        """
        # 新しいグラバーハンドルを作成
        self._hGrabber = self.ic.IC_CreateGrabber()

        if config_file_path is not None:
            self.load_properties(config_file_path, should_open_device=True)

        if not self.ic.IC_IsDevValid(self._hGrabber):  # 設定ファイルが存在しない場合にカメラを開く
            self._hGrabber = self._select_device()

        if self.ic.IC_IsDevValid(self._hGrabber):
            self._setup_device()
            logger.info(f"Device {self.userdata.devicename} open")
            return True
        else:
            self._handle_device_open_error()
            return False

    def load_properties(self, config_file_path, should_open_device=False):
        """ 設定ファイルのロード

        上手く読み込めなかったらエラーメッセージ
        設定ファイルを切り替える際もこの関数を使用する

        Args:
            config_file_path (str):***.xml 読み込むファイルの場所
            should_open_device (bool): OpenDeviceが 1 or 0

        """
        ret = self.ic.IC_LoadDeviceStateFromFileEx(self._hGrabber, tis.T(config_file_path), should_open_device)
        # 設定ファイルが存在しない場合、デバイスがない場合、xmlの形式が間違っている場合
        if ret == tis.IC_FILE_NOT_FOUND or ret == tis.IC_DEVICE_NOT_FOUND or ret == tis.IC_WRONG_XML_FORMAT or \
                ret == tis.IC_WRONG_INCOMPATIBLE_XML:
            logger.error("Can not load config")

    def start(self, create_window=False):
        """ 画像の取得の開始

        Args:
            create_window (bool): Trueだと、tisgrabberがウィンドウを生成してくれる
        """
        self.ic.IC_StartLive(self._hGrabber, create_window)

        # 画像の解像度・フォーマットを取得
        self._get_image_description()

        # 取得した画像をそのままnumpy配列に変換するとなぜか上下反転するので、反転させるフィルターを有効化しておく
        self._flip_image()

    def stop(self):
        """ 画像の取得の停止 """
        if self.ic.IC_IsLive(self._hGrabber):
            self.ic.IC_StopLive(self._hGrabber)

    def release(self):
        """ 終了処理 """
        if self.ic.IC_IsDevValid(self._hGrabber):
            self.ic.IC_StopLive(self._hGrabber)
            self.ic.IC_ReleaseGrabber(self._hGrabber)

    def reconnect_wait(self):
        """ 再接続待ち """
        logger.debug('reconnect')
        if self.userdata.connected is False:
            self.release()
            while not self.userdata.connected:
                logger.debug('wait')
                if cv2.waitKey(1) == 27:
                    break
                if self.open_device(self._config_file_path):
                    self.start()
                time.sleep(0.5)

    def show_property_dialog(self):
        """ 設定変更ウィンドウを表示 """
        dialog_thread = threading.Thread(target=self.ic.IC_ShowPropertyDialog, args=(self._hGrabber,))
        dialog_thread.start()

    def list_available_properties(self):
        """設定可能な項目一覧を表示。なぜかライブ中だと表示できない。"""
        self.ic.IC_printItemandElementNames(self._hGrabber)

    def save_properties(self, file_path):
        """ 設定ファイルの保存。XML形式。

        Args:
            file_path (str): ***.xml 保存する場所

        """
        self.ic.IC_SaveDeviceStateToFile(self._hGrabber, tis.T(file_path))

    def _select_device(self):
        """ デバイスを選択または開く """
        devicecount = self.ic.IC_GetDeviceCount()
        if devicecount > 1:  # カメラが２つ以上ある場合はダイアログで選択
            return self.ic.IC_ShowDeviceSelectionDialog(None)
        elif devicecount == 1:
            unique_name = self.ic.IC_GetUniqueNamefromList(0)
            self.ic.IC_OpenDevByUniqueName(self._hGrabber, unique_name)  # カメラ接続
            return self._hGrabber
        else:
            return None

    def _setup_device(self):
        """ デバイスの設定 """
        self.userdata.devicename = self.ic.IC_GetDeviceName(self._hGrabber).decode('utf-8', 'ignore')
        self.userdata.connected = True

        self.ic.IC_SetCallbacks(self._hGrabber,
                                self.frameReadyCallbackFunc, None,
                                self.deviceLostCallbackFunc, self.userdata)

    def _flip_image(self):
        """ 画像を反転させる

        取得した画像をnumpy配列に変換するとなぜか上下反転されてるので、反転フィルターを事前に加える
        """
        _filter = tis.HFRAMEFILTER()
        self.ic.IC_CreateFrameFilter(tis.T("Rotate Flip"), _filter)
        self.ic.IC_AddFrameFilterToDevice(self._hGrabber, _filter)
        self.ic.IC_FrameFilterSetParameterBoolean(_filter, tis.T("Flip V"), 1)

    def _get_image_description(self):
        """ 画像の解像度・フォーマットを取得する """
        self.ic.IC_GetImageDescription(self._hGrabber,
                                       self._width, self._height, self._bits_per_pixel, self._color_format)
        self._channel = int(self._bits_per_pixel.value / 8.0)
        self._buffer_size = self._width.value * self._height.value * self._bits_per_pixel.value

    @property
    def width(self):
        """ 画像の幅 """
        return self._width.value

    @property
    def height(self):
        """ 画像の高さ """
        return self._height.value

    @property
    def userdate(self):
        """ カメラの情報 """
        return self.userdata

    def set_video_format(self, format: str):
        """解像度を設定する"""
        try:
            self.ic.IC_SetVideoFormat(self._hGrabber, tis.T(format))
            return True
        except Exception as e:
            logger.error(f"Failed to set VideoFormat: {e}")
            return False

    def get_video_format(self):
        """解像度を取得する"""
        try:
            format = ctypes.c_char_p()
            self.ic.IC_GetVideoFormat(self._hGrabber, format)
            return format.value.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to get VideoFormat: {e}")
            return False

    def get_color_format(self):
        """カラーフォーマットを取得する"""
        try:
            # FOURCCはカメラのカラーフォーマットから推測
            if hasattr(self, "_color_format"):
                fmt = self._color_format.value.decode('utf-8') if hasattr(self._color_format, "value") else str(
                    self._color_format)
                # 例: "RGB24" -> cv2.VideoWriter_fourcc(*'RGB3')
                if fmt.startswith("RGB"):
                    return cv2.VideoWriter_fourcc(*'RGB3')
                elif fmt.startswith("Y800"):
                    return cv2.VideoWriter_fourcc(*'Y800')
                elif fmt.startswith("Y16"):
                    return cv2.VideoWriter_fourcc(*'Y16')
                elif fmt.startswith("UYVY"):
                    return cv2.VideoWriter_fourcc(*'UYVY')
                # 他のフォーマットも必要に応じて追加
            return None
        except Exception as e:
            logger.error(f"Failed to get ColorFormat: {e}")
            return False

    def _set_property_value(self, property_name: str, element_name: str, value) -> bool:
        """共通プロパティ設定用内部メソッド"""
        if self.ic.IC_IsLive(self._hGrabber):
            logger.warning("プロパティはライブ中には設定できません")
            return False
        try:
            self.ic.IC_SetPropertyValue(self._hGrabber, tis.T(property_name), tis.T(element_name), ctypes.c_float(value))
            return True
        except Exception as e:
            logger.error(f"Failed to set {property_name}: {e}")
            return False

    def _get_property_value(self, property_name: str, element_name: str):
        """共通プロパティ取得用内部メソッド"""
        value = ctypes.c_float()
        self.ic.IC_GetPropertyAbsoluteValue(self._hGrabber, tis.T(property_name), tis.T(element_name), value)
        return value.value

    def _set_property_absolute_value(self, property_name: str, element_name: str, value) -> bool:
        """共通プロパティ絶対値設定用内部メソッド"""
        if self.ic.IC_IsLive(self._hGrabber):
            logger.warning("プロパティはライブ中には設定できません")
            return False
        try:
            self.ic.IC_SetPropertyAbsoluteValue(self._hGrabber, tis.T(property_name), tis.T(element_name), ctypes.c_float(value))
            return True
        except Exception as e:
            logger.error(f"Failed to set absolute {property_name}: {e}")
            return False

    def _get_property_absolute_value(self, property_name: str, element_name: str):
        """共通プロパティ絶対値取得用内部メソッド"""
        value = ctypes.c_float()
        self.ic.IC_GetPropertyAbsoluteValue(self._hGrabber, tis.T(property_name), tis.T(element_name), value)
        return value.value

    def _set_property_switch(self, property_name: str, element_name: str, enable: bool) -> bool:
        """共通プロパティスイッチ設定用内部メソッド"""
        if self.ic.IC_IsLive(self._hGrabber):
            logger.warning("プロパティはライブ中には設定できません")
            return False
        try:
            self.ic.IC_SetPropertySwitch(self._hGrabber, tis.T(property_name), tis.T(element_name), ctypes.c_long(1 if enable else 0))
            return True
        except Exception as e:
            logger.error(f"Failed to set switch {property_name}: {e}")
            return False

    def _get_property_switch(self, property_name: str, element_name: str) -> bool:
        """共通プロパティスイッチ取得用内部メソッド"""
        try:
            value = ctypes.c_long()
            self.ic.IC_GetPropertySwitch(self._hGrabber, tis.T(property_name), tis.T(element_name), value)
            return value.value == 1
        except Exception as e:
            logger.error(f"Failed to get switch {property_name}: {e}")
            return False

    def _get_property_range(self, property_name: str, element_name: str):
        """共通プロパティ範囲取得用内部メソッド"""
        try:
            min_value = ctypes.c_float()
            max_value = ctypes.c_float()
            self.ic.IC_GetPropertyAbsoluteValueRange(self._hGrabber, tis.T(property_name), tis.T(element_name), min_value, max_value)
            return min_value.value, max_value.value
        except Exception as e:
            logger.error(f"Failed to get range {property_name}: {e}")
            return

    def set_brightness(self, value: float):
        """明るさ(Brightness)を設定する"""
        return self._set_property_value("Brightness", "Value", value)

    def get_brightness(self):
        """明るさ(Brightness)を取得する"""
        return self._get_property_value("Brightness", "Value")

    def set_contrast(self, value: float):
        """コントラスト(Contrast)を設定する"""
        return self._set_property_value("Contrast", "Value", value)

    def get_contrast(self):
        """コントラスト(Contrast)を取得する"""
        return self._get_property_value("Contrast", "Value")

    def set_hue(self, value: float):
        """色相(Hue)を設定する"""
        return self._set_property_value("Hue", "Value", value)

    def get_hue(self):
        """色相(Hue)を取得する"""
        return self._get_property_value("Hue", "Value")

    def set_saturation(self, value: float):
        """彩度(Saturation)を設定する"""
        return self._set_property_value("Saturation", "Value", value)

    def get_saturation(self):
        """彩度(Saturation)を取得する"""
        return self._get_property_value("Saturation", "Value")

    def set_sharpness(self, value: float):
        """シャープネス(Sharpness)を設定する"""
        return self._set_property_value("Sharpness", "Value", value)

    def get_sharpness(self):
        """シャープネス(Sharpness)を取得する"""
        return self._get_property_value("Sharpness", "Value")

    def set_gamma(self, value):
        """ガンマ(Gamma)を設定する"""
        return self._set_property_value("Gamma", "Value", value)

    def get_gamma(self):
        """ガンマ(Gamma)を取得する"""
        return self._get_property_value("Gamma", "Value")

    def set_whitebalance_auto(self, enable: bool = True):
        """ホワイトバランス自動(WhiteBalanceAuto)を設定する"""
        return self._set_property_switch("WhiteBalance", "Auto", enable)

    def get_whitebalance_auto(self):
        """ホワイトバランス自動(WhiteBalanceAuto)を取得する"""
        return self._get_property_switch("WhiteBalance", "Auto")

    def set_whitebalance(self, value: list) -> bool:
        """ホワイトバランス(WhiteBalance)を設定する"""
        try:
            self.set_whitebalance_auto(False)
            self._set_property_absolute_value("WhiteBalance", "White Balance Red", value[0])
            self._set_property_absolute_value("WhiteBalance", "White Balance Green", value[1])
            self._set_property_absolute_value("WhiteBalance", "White Balance Blue", value[2])
            return True
        except Exception as e:
            logger.error(f"Failed to set WhiteBalance: {e}")
            return False

    def set_whitebalance_red(self, value: float):
        """ホワイトバランス(WhiteBalance)を設定する"""
        try:
            self.set_whitebalance_auto(False)
            return self._set_property_absolute_value("WhiteBalance", "White Balance Red", value)
        except Exception as e:
            logger.error(f"Failed to set WhiteBalance: {e}")
            return False

    def set_whitebalance_green(self, value: float):
        """ホワイトバランス(WhiteBalance)を設定する"""
        try:
            self.set_whitebalance_auto(False)
            return self._set_property_absolute_value("WhiteBalance", "White Balance Green", value)
        except Exception as e:
            logger.error(f"Failed to set WhiteBalance: {e}")
            return False

    def set_whitebalance_blue(self, value: float):
        """ホワイトバランス(WhiteBalance)を設定する"""
        try:
            self.set_whitebalance_auto(False)
            return self._set_property_absolute_value("WhiteBalance", "White Balance Blue", value)
        except Exception as e:
            logger.error(f"Failed to set WhiteBalance: {e}")
            return False

    def get_whitebalance(self) -> tuple:
        """ホワイトバランス(WhiteBalance)を取得する"""
        whiteBalanceRed = self._get_property_absolute_value("WhiteBalance", "White Balance Red")
        whiteBalanceGreen = self._get_property_absolute_value("WhiteBalance", "White Balance Green")
        whiteBalanceBlue = self._get_property_absolute_value("WhiteBalance", "White Balance Blue")

        return (whiteBalanceRed, whiteBalanceGreen, whiteBalanceBlue)

    def get_whitebalance_red(self):
        """ホワイトバランス(WhiteBalance)を取得する"""
        whiteBalanceRed = self._get_property_absolute_value("WhiteBalance", "White Balance Red")
        return whiteBalanceRed

    def get_whitebalance_green(self):
        """ホワイトバランス(WhiteBalance)を取得する"""
        whiteBalanceGreen = self._get_property_absolute_value("WhiteBalance", "White Balance Green")
        return whiteBalanceGreen

    def get_whitebalance_blue(self):
        """ホワイトバランス(WhiteBalance)を取得する"""
        whiteBalanceBlue = self._get_property_absolute_value("WhiteBalance", "White Balance Blue")
        return whiteBalanceBlue

    def set_gain_auto(self, enable: bool = True):
        """ゲイン自動(GainAuto)を設定する"""
        return self._set_property_switch("Gain", "Auto", enable)

    def get_gain_auto(self):
        """ゲイン自動(GainAuto)を取得する"""
        return self._get_property_switch("Gain", "Auto")

    def set_gain(self, value):
        """ゲイン(Gain)を設定する"""
        try:
            self.set_gain_auto(False)
            return self._set_property_absolute_value("Gain", "Value", value)
        except Exception as e:
            logger.error(f"Failed to set Gain: {e}")
            return False

    def get_gain(self):
        """ゲイン(Gain)を取得する"""
        gainmin, gainmax = self._get_property_range("Gain", "Value")
        gain = self._get_property_absolute_value("Gain", "Value")

        return gain, gainmin, gainmax

    def set_exposure_auto(self, enable: bool = True):
        """露光時間自動(ExposureAuto)を設定する"""
        return self._set_property_switch("Exposure", "Auto", enable)

    def get_exposure_auto(self):
        """露光時間自動(ExposureAuto)を取得する"""
        return self._get_property_switch("Exposure", "Auto")

    def set_exposure(self, value: float):
        """露光時間(Exposure)を設定する"""
        try:
            self.set_exposure_auto(False)
            return self._set_property_absolute_value("Exposure", "Value", value)
        except Exception as e:
            logger.error(f"Failed to set Exposure: {e}")
            return False

    def get_exposure(self):
        """露光時間(Exposure)を取得する"""
        expmin, expmax = self._get_property_range("Exposure", "Value")
        exposure = self._get_property_absolute_value("Exposure", "Value")

        return exposure, expmin, expmax

    def set_frame_rate(self, value: float):
        """フレームレート(FrameRate)を設定する"""
        if self.ic.IC_IsDevValid(self._hGrabber):
            self.ic.IC_SetFrameRate(self._hGrabber, ctypes.c_float(value))
            return True
        else:
            return False

    def get_frame_rate(self):
        """フレームレート(FrameRate)を取得する"""
        fps = ctypes.c_float()
        self.ic.IC_GetFrameRate(self._hGrabber, fps)
        return fps.value

    def set_focus(self, value):
        """フォーカス(Focus)を設定する"""
        return False

    def set_focus_auto(self, enable: bool = True):
        """オートフォーカス(FocusAuto)を設定する"""
        return False

    def set_flip_horizontal(self, enable: bool = True):
        """水平反転(FlipHorizontal)を設定する"""
        enable = 1 if enable else 0
        self.ic.IC_SetPropertySwitch(self._hGrabber, tis.T("Flip Horizontal"), tis.T("Enable"), enable)
        print(enable)
        auto = ctypes.c_long()
        self.ic.IC_GetPropertySwitch(self._hGrabber, tis.T("Flip Horizontal"), tis.T("Enable"), auto)
        print(auto.value)
        return True

    def set_flip_vertical(self, enable: bool = True):
        """垂直反転(FlipVertical)を設定する"""
        enable = 1 if enable else 0
        self.ic.IC_SetPropertySwitch(self._hGrabber, tis.T("Flip Verical"), tis.T("Enable"), enable)
        return True

    def set(self, prop_id, value):
        """
        cv2.CAP_PROP_* に対応する値を設定する

        Args:
            prop_id (int): cv2.CAP_PROP_* のID
            value: 設定する値
        """
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            return False
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return False
        elif prop_id == cv2.CAP_PROP_FPS:
            return self.set_frame_rate(value)
        elif prop_id == cv2.CAP_PROP_BRIGHTNESS:
            return self.set_brightness(value)
        elif prop_id == cv2.CAP_PROP_CONTRAST:
            return self.set_contrast(value)
        elif prop_id == cv2.CAP_PROP_SATURATION:
            return self.set_saturation(value)
        elif prop_id == cv2.CAP_PROP_HUE:
            return self.set_hue(value)
        elif prop_id == cv2.CAP_PROP_GAIN:
            return self.set_gain(value)
        elif prop_id == cv2.CAP_PROP_EXPOSURE:
            return self.set_exposure(value)
        elif prop_id == cv2.CAP_PROP_GAMMA:
            return self.set_gamma(value)
        elif prop_id == cv2.CAP_PROP_SHARPNESS:
            return self.set_sharpness(value)
        elif prop_id == cv2.CAP_PROP_WHITE_BALANCE_BLUE_U:
            return self.set_whitebalance_blue(value)
        elif prop_id == cv2.CAP_PROP_WHITE_BALANCE_RED_V:
            return self.set_whitebalance_red(value)
        elif prop_id == cv2.CAP_PROP_AUTOFOCUS:
            return self.set_focus_auto(value)
        elif prop_id == cv2.CAP_PROP_FOCUS:
            return self.set_focus(value)
        else:
            return False

    def get(self, prop_id):
        """
        cv2.CAP_PROP_* に対応する値を返す

        Args:
            prop_id (int): cv2.CAP_PROP_* のID

        Returns:
            対応する値、または None
        """
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            return self.width
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return self.height
        elif prop_id == cv2.CAP_PROP_FPS:
            return self.get_frame_rate()
        elif prop_id == cv2.CAP_PROP_FOURCC:
            return self.get_color_format()
        elif prop_id == cv2.CAP_PROP_FRAME_COUNT:
            # ライブカメラなのでフレーム数は不定
            return 0
        elif prop_id == cv2.CAP_PROP_BRIGHTNESS:
            return self.get_brightness()
        elif prop_id == cv2.CAP_PROP_CONTRAST:
            return self.get_contrast()
        elif prop_id == cv2.CAP_PROP_SATURATION:
            return self.get_saturation()
        elif prop_id == cv2.CAP_PROP_HUE:
            return self.get_hue()
        elif prop_id == cv2.CAP_PROP_GAIN:
            return self.get_gain()
        elif prop_id == cv2.CAP_PROP_EXPOSURE:
            return self.get_exposure()
        elif prop_id == cv2.CAP_PROP_GAMMA:
            return self.get_gamma()
        elif prop_id == cv2.CAP_PROP_SHARPNESS:
            return self.get_sharpness()
        elif prop_id == cv2.CAP_PROP_WHITE_BALANCE_BLUE_U:
            return self.get_whitebalance_blue()
        elif prop_id == cv2.CAP_PROP_WHITE_BALANCE_RED_V:
            return self.get_whitebalance_red()
        elif prop_id == cv2.CAP_PROP_AUTOFOCUS:
            return self.get_focus_auto()
        elif prop_id == cv2.CAP_PROP_FOCUS:
            return self.get_focus()
        else:
            return None


if __name__ == '__main__':
    import cv2

    config_file1 = ""
    config_file2 = ""

    cap = MyVideoCapture(config_file1)

    window_width = 1200
    window_height = 900

    print(cap.userdata.devicename)
    cv2.namedWindow("config 1", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("config 1", window_width, window_height)
    cv2.namedWindow("config 2", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("config 2", window_width, window_height)
    while True:
        if cap.userdata.connected is False:
            while not cap.userdata.connected:
                cap.start()
        img = cap.read()

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
        elif k == ord("l"):
            cap.list_available_properties()

    cv2.destroyAllWindows()
    cap.release()
