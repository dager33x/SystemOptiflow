"""Validate local video inputs before replacing any running camera sources."""
from pathlib import Path

import cv2

VIDEO_FILTER = 'Videos (*.mp4 *.avi *.mkv *.mov *.m4v *.wmv *.webm *.mpeg *.mpg);;All files (*)'
LANE_NAMES = ('North', 'South', 'East', 'West')


def is_video_source(source):
    return (isinstance(source, str) and source != 'simulation'
            and not source.lower().startswith(('rtsp://', 'http://', 'https://')))


def validate_video_sources(sources):
    """Decode a frame from every file, returning absolute paths only on success.

    Run off the UI thread. No camera state changes until the whole batch passes.
    File extensions alone cannot establish that OpenCV supports a video's codec.
    """
    if not sources or any(type(lane) is not int or lane not in range(4) for lane in sources):
        raise ValueError('Choose a video for at least one of the four cameras.')
    validated = {}
    for lane, filename in sources.items():
        cap = None
        try:
            path = Path(filename).expanduser().resolve(strict=True)
            if not path.is_file():
                raise ValueError('Select a video file, not a folder.')
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                raise ValueError('This video could not be opened. Try an MP4 (H.264) or AVI video.')
            ok, frame = cap.read()
            if not ok or frame is None or frame.size == 0:
                raise ValueError('This video has no readable frames. Try another video or export it as MP4 (H.264).')
            validated[lane] = str(path)
        except (OSError, ValueError, cv2.error) as error:
            raise ValueError(f'{LANE_NAMES[lane]} camera: {error}') from error
        finally:
            if cap is not None:
                cap.release()
    return validated
