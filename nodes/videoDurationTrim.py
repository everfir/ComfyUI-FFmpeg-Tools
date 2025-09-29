import os
import subprocess
import tempfile
import shutil
from io import BytesIO
from ..func import set_file_name, video_type


class VideoDurationTrim:
    """
    根据指定时长裁剪视频，从0秒开始裁剪到指定的duration秒
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO", {}),  # ComfyUI标准视频输入
                "duration": (
                    "FLOAT",
                    {
                        "default": 10.0,
                        "min": 0.1,
                        "max": 3600.0,  # 最大1小时
                        "step": 0.1,
                        "display": "number",
                        "tooltip": "裁剪时长（秒），从视频开始位置裁剪",
                    },
                ),
            },
            "optional": {
                "output_path": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "可选的输出路径，如果为空则使用临时目录",
                    },
                ),
            },
        }

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("trimmed_video",)
    FUNCTION = "trim_video_by_duration"
    OUTPUT_NODE = False  # 设为False，因为我们返回VIDEO类型而不是最终输出
    CATEGORY = "🔥FFmpeg"

    def trim_video_by_duration(self, video, duration, output_path=""):
        """
        根据duration裁剪视频，从0秒开始到指定时长
        """
        temp_input_path = None
        temp_output_path = None

        try:
            # 创建临时目录
            temp_dir = tempfile.mkdtemp(prefix="comfyui_video_trim_")

            # 处理输入视频 - 将VIDEO类型保存到临时文件
            if hasattr(video, "save_video"):
                # 如果video对象有save_video方法
                temp_input_path = os.path.join(temp_dir, "input_video.mp4")
                video.save_video(temp_input_path)
            elif hasattr(video, "write_to_file"):
                # 如果video对象有write_to_file方法
                temp_input_path = os.path.join(temp_dir, "input_video.mp4")
                video.write_to_file(temp_input_path)
            elif isinstance(video, (str, os.PathLike)):
                # 如果是文件路径
                temp_input_path = str(video)
                if not os.path.exists(temp_input_path):
                    raise ValueError(f"视频文件不存在: {temp_input_path}")
            elif hasattr(video, "read"):
                # 如果是文件对象或BytesIO
                temp_input_path = os.path.join(temp_dir, "input_video.mp4")
                with open(temp_input_path, "wb") as f:
                    if hasattr(video, "getvalue"):
                        f.write(video.getvalue())
                    else:
                        f.write(video.read())
            else:
                # 尝试其他可能的VIDEO类型处理方式
                temp_input_path = os.path.join(temp_dir, "input_video.mp4")
                # 假设video对象可以直接写入文件
                try:
                    with open(temp_input_path, "wb") as f:
                        if hasattr(video, "tobytes"):
                            f.write(video.tobytes())
                        else:
                            # 最后的尝试 - 假设它是某种可迭代的字节数据
                            f.write(bytes(video))
                except Exception as e:
                    raise ValueError(
                        f"无法处理输入的视频格式: {type(video)}, 错误: {str(e)}"
                    )

            # 验证输入文件
            if not os.path.exists(temp_input_path):
                raise ValueError("无法创建临时输入文件")

            # 验证是否为视频文件
            if not temp_input_path.lower().endswith(video_type()):
                # 尝试重命名为.mp4
                new_temp_input = temp_input_path + ".mp4"
                os.rename(temp_input_path, new_temp_input)
                temp_input_path = new_temp_input

            # 验证duration参数
            if duration <= 0:
                raise ValueError("duration必须大于0")

            # 确定输出路径
            if output_path and output_path.strip():
                output_path = os.path.abspath(output_path.strip())
                if os.path.isdir(output_path):
                    file_name = set_file_name(temp_input_path)
                    temp_output_path = os.path.join(output_path, file_name)
                else:
                    temp_output_path = output_path
                    # 确保输出目录存在
                    os.makedirs(os.path.dirname(temp_output_path), exist_ok=True)
            else:
                # 使用临时目录
                file_name = set_file_name(temp_input_path)
                temp_output_path = os.path.join(temp_dir, f"trimmed_{file_name}")

            # 构建ffmpeg命令 - 从0秒开始裁剪指定时长
            # 使用 -t 参数指定持续时间，而不是结束时间
            command = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-i",
                temp_input_path,  # 输入视频路径
                "-ss",
                "0",  # 从0秒开始
                "-t",
                str(duration),  # 持续时长
                "-c",
                "copy",  # 复制流，避免重新编码（更快）
                temp_output_path,
            ]

            print(f"执行FFmpeg命令: {' '.join(command)}")

            # 执行命令并检查错误
            result = subprocess.run(
                command, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True
            )

            # 检查返回码
            if result.returncode != 0:
                print(f"FFmpeg错误输出: {result.stderr}")
                # 如果-c copy失败，尝试重新编码
                print("尝试使用重新编码模式...")
                command_reencode = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    temp_input_path,
                    "-ss",
                    "0",
                    "-t",
                    str(duration),
                    "-c:v",
                    "libx264",  # 重新编码视频
                    "-c:a",
                    "aac",  # 重新编码音频
                    temp_output_path,
                ]

                result = subprocess.run(
                    command_reencode,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                )

                if result.returncode != 0:
                    raise ValueError(f"FFmpeg执行失败: {result.stderr}")

            print(f"视频裁剪完成: {temp_output_path}")

            # 验证输出文件是否存在
            if not os.path.exists(temp_output_path):
                raise ValueError("裁剪后的视频文件未生成")

            # 读取裁剪后的视频并转换为VIDEO类型
            # 这里需要根据ComfyUI的VIDEO类型实现来调整
            try:
                # 方法1: 尝试使用VideoFromFile (如Luma节点)
                from comfy_api.input_impl.video_types import VideoFromFile

                with open(temp_output_path, "rb") as f:
                    video_data = BytesIO(f.read())
                trimmed_video = VideoFromFile(video_data)

            except ImportError:
                # 方法2: 如果没有VideoFromFile，尝试其他方式
                try:
                    # 读取为字节数据，让ComfyUI自动处理
                    with open(temp_output_path, "rb") as f:
                        trimmed_video = f.read()
                except Exception as e:
                    # 方法3: 返回文件路径
                    trimmed_video = temp_output_path
                    print(f"返回文件路径作为VIDEO类型: {temp_output_path}")

            return (trimmed_video,)

        except Exception as e:
            error_msg = f"视频裁剪失败: {str(e)}"
            print(error_msg)
            raise ValueError(error_msg)

        finally:
            # 清理临时文件（可选，根据需要决定是否保留）
            # 注意：如果返回的是文件路径，不应该删除临时文件
            if temp_dir and os.path.exists(temp_dir):
                try:
                    # 如果输出路径不在临时目录中，可以安全删除临时目录
                    if (
                        output_path
                        and output_path.strip()
                        and not temp_output_path.startswith(temp_dir)
                    ):
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        print(f"清理临时目录: {temp_dir}")
                    # 否则保留临时文件，由系统稍后清理
                except Exception as e:
                    print(f"清理临时文件时出错: {str(e)}")
