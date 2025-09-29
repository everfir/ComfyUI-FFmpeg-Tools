import os
import subprocess
import tempfile
import shutil
from io import BytesIO
from ..func import set_file_name, video_type

# 导入ComfyUI的文件路径管理
try:
    import folder_paths

    COMFYUI_INTEGRATION = True
except ImportError:
    COMFYUI_INTEGRATION = False


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
                        "tooltip": "可选的输出路径。留空使用临时目录，输入'output'使用ComfyUI输出目录",
                    },
                ),
                "save_to_output": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "是否保存到ComfyUI的output目录（会被ComfyUI管理，不会自动清理）",
                    },
                ),
            },
        }

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("trimmed_video",)
    FUNCTION = "trim_video_by_duration"
    OUTPUT_NODE = False  # 设为False，因为我们返回VIDEO类型而不是最终输出
    CATEGORY = "🔥FFmpeg"

    def trim_video_by_duration(
        self, video, duration, output_path="", save_to_output=False
    ):
        """
        根据duration裁剪视频，从0秒开始到指定时长
        """
        temp_input_path = None
        temp_output_path = None

        try:
            # 创建临时目录 - 优先使用ComfyUI的temp目录
            if COMFYUI_INTEGRATION:
                comfyui_temp_dir = folder_paths.get_temp_directory()
                os.makedirs(comfyui_temp_dir, exist_ok=True)
                temp_dir = tempfile.mkdtemp(prefix="video_trim_", dir=comfyui_temp_dir)
                print(f"使用ComfyUI temp目录: {temp_dir}")
            else:
                temp_dir = tempfile.mkdtemp(prefix="comfyui_video_trim_")
                print(f"使用系统temp目录: {temp_dir}")

            # 处理输入视频 - 将VIDEO类型保存到临时文件
            if hasattr(video, "save_video"):
                # 如果video对象有save_video方法
                temp_input_path = os.path.join(temp_dir, "input_video.mp4")
                video.save_video(temp_input_path)
            elif hasattr(video, "write_to_file"):
                # 如果video对象有write_to_file方法
                temp_input_path = os.path.join(temp_dir, "input_video.mp4")
                video.write_to_file(temp_input_path)
            elif hasattr(video, "save") and callable(getattr(video, "save")):
                # 处理VideoFromComponents等有save方法的对象
                temp_input_path = os.path.join(temp_dir, "input_video.mp4")
                video.save(temp_input_path)
            elif hasattr(video, "write_to") and callable(getattr(video, "write_to")):
                # 处理可能有write_to方法的视频对象
                temp_input_path = os.path.join(temp_dir, "input_video.mp4")
                with open(temp_input_path, "wb") as f:
                    video.write_to(f)
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
                # 处理VideoFromComponents等复杂视频对象
                temp_input_path = os.path.join(temp_dir, "input_video.mp4")
                saved = False
                error_messages = []

                # 尝试多种可能的保存方法
                save_methods = [
                    ("save", lambda v, p: v.save(p)),
                    ("write_video", lambda v, p: v.write_video(p)),
                    ("to_file", lambda v, p: v.to_file(p)),
                    ("export", lambda v, p: v.export(p)),
                    ("save_to", lambda v, p: v.save_to(p)),
                ]

                for method_name, method_func in save_methods:
                    if hasattr(video, method_name):
                        try:
                            method_func(video, temp_input_path)
                            saved = True
                            print(f"成功使用 {method_name} 方法保存视频")
                            break
                        except Exception as e:
                            error_messages.append(f"{method_name}: {str(e)}")
                            continue

                # 如果所有保存方法都失败了，尝试字节数据方法
                if not saved:
                    try:
                        with open(temp_input_path, "wb") as f:
                            if hasattr(video, "tobytes"):
                                f.write(video.tobytes())
                                saved = True
                                print("成功使用 tobytes 方法保存视频")
                            elif hasattr(video, "read"):
                                video_data = video.read()
                                f.write(video_data)
                                saved = True
                                print("成功使用 read 方法保存视频")
                    except Exception as e:
                        error_messages.append(f"tobytes/read: {str(e)}")

                if not saved:
                    available_methods = [
                        attr for attr in dir(video) if not attr.startswith("_")
                    ]
                    error_msg = f"无法处理输入的视频格式: {type(video)}\n"
                    error_msg += f"尝试的方法失败: {'; '.join(error_messages)}\n"
                    error_msg += f"对象可用方法: {', '.join(available_methods[:20])}..."
                    raise ValueError(error_msg)

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
            file_name = set_file_name(temp_input_path)

            if save_to_output and COMFYUI_INTEGRATION:
                # 保存到ComfyUI的output目录
                output_dir = folder_paths.get_output_directory()
                video_subdir = os.path.join(output_dir, "video_trim")
                os.makedirs(video_subdir, exist_ok=True)
                temp_output_path = os.path.join(video_subdir, f"trimmed_{file_name}")
                print(f"保存到ComfyUI output目录: {temp_output_path}")
            elif output_path and output_path.strip():
                # 用户指定路径
                if output_path.strip().lower() == "output" and COMFYUI_INTEGRATION:
                    # 特殊关键词：使用ComfyUI output目录
                    output_dir = folder_paths.get_output_directory()
                    temp_output_path = os.path.join(output_dir, f"trimmed_{file_name}")
                else:
                    # 用户自定义路径
                    output_path = os.path.abspath(output_path.strip())
                    if os.path.isdir(output_path):
                        temp_output_path = os.path.join(
                            output_path, f"trimmed_{file_name}"
                        )
                    else:
                        temp_output_path = output_path
                        # 确保输出目录存在
                        os.makedirs(os.path.dirname(temp_output_path), exist_ok=True)
                print(f"保存到用户指定路径: {temp_output_path}")
            else:
                # 使用临时目录
                temp_output_path = os.path.join(temp_dir, f"trimmed_{file_name}")
                print(f"保存到临时目录: {temp_output_path}")

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

                # VideoFromFile 期望文件路径，不是BytesIO
                trimmed_video = VideoFromFile(temp_output_path)
                print(f"成功使用VideoFromFile创建视频对象: {temp_output_path}")

            except ImportError:
                # 方法2: 如果没有VideoFromFile，尝试其他方式
                try:
                    # 尝试使用BytesIO方式
                    with open(temp_output_path, "rb") as f:
                        video_data = BytesIO(f.read())
                        # 尝试其他可能的VIDEO构造方式
                        from comfy_api.latest._input_impl.video_types import (
                            VideoFromFile as VideoFromFileLatest,
                        )

                        trimmed_video = VideoFromFileLatest(video_data)
                        print("成功使用latest VideoFromFile创建视频对象")
                except Exception as e:
                    print(f"BytesIO方式失败: {e}")
                    # 方法3: 返回文件路径
                    trimmed_video = temp_output_path
                    print(f"返回文件路径作为VIDEO类型: {temp_output_path}")
            except Exception as e:
                print(f"VideoFromFile创建失败: {e}")
                # 尝试备用方案
                try:
                    # 尝试使用latest版本
                    from comfy_api.latest._input_impl.video_types import (
                        VideoFromFile as VideoFromFileLatest,
                    )

                    trimmed_video = VideoFromFileLatest(temp_output_path)
                    print("成功使用latest VideoFromFile创建视频对象")
                except Exception as e2:
                    print(f"latest VideoFromFile也失败: {e2}")
                    # 最后的备用方案：返回文件路径
                    trimmed_video = temp_output_path
                    print(f"返回文件路径作为VIDEO类型: {temp_output_path}")

            return (trimmed_video,)

        except Exception as e:
            error_msg = f"视频裁剪失败: {str(e)}"
            print(error_msg)
            raise ValueError(error_msg)

        finally:
            # 智能临时文件清理策略
            if temp_dir and os.path.exists(temp_dir):
                try:
                    should_cleanup = False

                    if COMFYUI_INTEGRATION:
                        # 使用ComfyUI temp目录时的清理策略
                        if (
                            output_path
                            and output_path.strip()
                            and temp_output_path
                            and not temp_output_path.startswith(temp_dir)
                        ):
                            # 用户指定了输出路径且文件已复制到用户目录，可以清理
                            should_cleanup = True
                            cleanup_reason = "文件已保存到用户指定路径"
                        else:
                            # 文件在ComfyUI temp目录中，让ComfyUI自动清理
                            should_cleanup = False
                            cleanup_reason = "由ComfyUI自动清理（启动时清理temp目录）"
                    else:
                        # 非ComfyUI环境，使用传统清理策略
                        if (
                            output_path
                            and output_path.strip()
                            and temp_output_path
                            and not temp_output_path.startswith(temp_dir)
                        ):
                            should_cleanup = True
                            cleanup_reason = "文件已保存到用户指定路径"
                        else:
                            should_cleanup = False
                            cleanup_reason = "保留临时文件供后续使用"

                    if should_cleanup:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        print(f"✅ 清理临时目录: {temp_dir} ({cleanup_reason})")
                    else:
                        print(f"📁 保留临时目录: {temp_dir} ({cleanup_reason})")

                except Exception as e:
                    print(f"❌ 清理临时文件时出错: {str(e)}")
