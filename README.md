# video-capture-for-tiscam
The Imaging Source社製USBカメラ用のVideoCapture。  
参考:  https://github.com/TheImagingSource/IC-Imaging-Control-Samples/tree/master/Python/tisgrabber

# 必要条件
opencv-python

# インストール方法
```
pip install git+https://このリポジトリのトークン@github.com/a-nemoto313/video-capture-for-tiscam.git 
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

# 運用方法
- 緊急の場合を除いて、master・developブランチに直接コミットしないこと。
- 許可なくmaster・developブランチにマージしないこと。以下のように運用。  
(githubを有料プランに切り替えれば許可したアカウントしかマージできなくなるらしい)  
  1. developからブランチを作成し、変更・修正をコミット
  2. そのブランチをリモートにプッシュ
  3. githubで該当のブランチを選択、Pull requestをクリック
  4. *base:* がdevelop、*compare:* が自分が作業したブランチになっていることを確認し、タイトルと説明を入力、Create Pull Requestをクリック。  
  5. レビュワーは変更内容を確認し、問題なければMerge pull request、delete the branch。

- 変更の際は必ずバージョンを更新。masterブランチ上のコミットにバージョン番号が同じものが存在しないように。[バージョンの付け方](https://note.com/a_iubimstudio/n/n65413e4ffcc9)
> ![バージョン](https://backlog.com/ja/git-tutorial/assets/img/stepup/stepup5_6.png)  
