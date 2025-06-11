import json
import asyncio
import datetime
import re
import os
import shutil
import requests
from dateutil import parser
from dateutil.relativedelta import relativedelta
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("kcjqr", "teheiw192", "课程提醒插件", "1.0.0", "https://github.com/teheiw192/kcjqr")
class CourseReminderPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        # 初始化数据存储
        self.course_data = {}  # 用户课程数据
        self.reminder_tasks = {}  # 提醒任务
        self.reminder_status = {}  # 提醒状态
        self.semester_config = {}  # 学期配置
        self.confirmation_status = {}  # 用户确认状态
        
        # 加载配置
        self.reminder_time = 30  # 默认提前30分钟提醒
        self.daily_notification_time = "23:00"  # 默认每天23:00发送通知
        self.api_base_url = "https://api.siliconflow.cn/v1"
        self.api_key = "sk-zxtmadhtngzchfjeuoasxfyjbvxnvunyqgyrusdwentlbjxo"
        self.model_name = "deepseek-ai/DeepSeek-V3"
        
        if config:
            self.reminder_time = config.get("reminder_time", 30)
            self.daily_notification_time = config.get("daily_notification_time", "23:00")
        
        # 创建数据目录
        self.data_dir = os.path.join("data", "kcjqr")
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 加载数据
        self.load_data()
        
        # 启动提醒任务
        asyncio.create_task(self.reminder_loop())
        asyncio.create_task(self.daily_notification_task())

    def load_data(self):
        """加载数据"""
        try:
            # 加载课程数据
            course_data_path = os.path.join(self.data_dir, "course_data.json")
            if os.path.exists(course_data_path):
                with open(course_data_path, "r", encoding="utf-8") as f:
                    self.course_data = json.load(f)
            
            # 加载提醒状态
            reminder_status_path = os.path.join(self.data_dir, "reminder_status.json")
            if os.path.exists(reminder_status_path):
                with open(reminder_status_path, "r", encoding="utf-8") as f:
                    self.reminder_status = json.load(f)
            
            # 加载学期配置
            semester_config_path = os.path.join(self.data_dir, "semester_config.json")
            if os.path.exists(semester_config_path):
                with open(semester_config_path, "r", encoding="utf-8") as f:
                    self.semester_config = json.load(f)
        except Exception as e:
            logger.error(f"加载数据失败: {str(e)}")

    def save_data(self):
        """保存数据"""
        try:
            # 保存课程数据
            course_data_path = os.path.join(self.data_dir, "course_data.json")
            with open(course_data_path, "w", encoding="utf-8") as f:
                json.dump(self.course_data, f, ensure_ascii=False, indent=2)
            
            # 保存提醒状态
            reminder_status_path = os.path.join(self.data_dir, "reminder_status.json")
            with open(reminder_status_path, "w", encoding="utf-8") as f:
                json.dump(self.reminder_status, f, ensure_ascii=False, indent=2)
            
            # 保存学期配置
            semester_config_path = os.path.join(self.data_dir, "semester_config.json")
            with open(semester_config_path, "w", encoding="utf-8") as f:
                json.dump(self.semester_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存数据失败: {str(e)}")

    @filter.message
    async def on_message(self, event: AstrMessageEvent) -> MessageEventResult:
        """处理消息"""
        user_id = event.user_id
        
        # 检查是否是图片或文件消息
        if event.message_type in ["image", "file"]:
            template = """【课程消息模板】

【姓名同学学年学期课程安排】

📚 基本信息

• 学校：XX大学（没有则不显示）

• 班级：XX班（没有则不显示）

• 专业：XX专业（没有则不显示）

• 学院：XX学院（没有则不显示）

🗓️ 每周课程详情
星期X

• 上课时间（节次和时间）：
课程名称
教师：老师姓名
上课地点：教室/场地
周次：具体周次

示例：
星期一
上课时间：第1-2节（08:00-09:40）
课程名称：如何找到富婆
教师：飘逸
上课地点150123
周次：1-16周

周末：无课程。

🌙 晚间课程

• 上课时间（节次和时间）：
课程名称
教师：老师姓名
上课地点：教室/场地
周次：具体周次

📌 重要备注

• 备注内容1

• 备注内容2

请留意课程周次及教室安排，合理规划学习时间！"""
            
            await event.reply(f"抱歉，我暂时无法识别图片和文件。\n\n由于作者比较穷，请您复制下方【课程消息模板】去豆包，将课程表图片或者文件和课程消息模板发送给豆包，让它生成后，再来发送给我。\n\n{template}")
            return MessageEventResult(handled=True)
        
        # 处理文本消息
        if event.message_type == "text":
            # 检查是否是确认消息
            if user_id in self.confirmation_status:
                if event.content.strip() in ["确认", "是的", "对", "正确"]:
                    self.reminder_status[user_id] = True
                    self.save_data()
                    await event.reply("已开启课程提醒功能！")
                    del self.confirmation_status[user_id]
                    return MessageEventResult(handled=True)
                elif event.content.strip() in ["取消", "不", "不对", "错误"]:
                    del self.confirmation_status[user_id]
                    await event.reply("已取消课程提醒功能。")
                    return MessageEventResult(handled=True)
            
            # 解析课程信息
            try:
                # 调用AI模型解析课程信息
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": self.model_name,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是一个专业的课程表解析助手，请将用户提供的课程信息解析为结构化的JSON格式。"
                        },
                        {
                            "role": "user",
                            "content": event.content
                        }
                    ]
                }
                
                response = requests.post(
                    f"{self.api_base_url}/chat/completions",
                    headers=headers,
                    json=data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    course_info = json.loads(result["choices"][0]["message"]["content"])
                    
                    # 保存课程信息
                    self.course_data[user_id] = course_info
                    self.save_data()
                    
                    # 发送确认消息
                    confirmation_msg = "请确认以下课程信息是否正确：\n\n"
                    confirmation_msg += self.format_course_info(course_info)
                    confirmation_msg += "\n\n请回复"确认"或"取消"。"
                    
                    self.confirmation_status[user_id] = True
                    await event.reply(confirmation_msg)
                else:
                    await event.reply("抱歉，课程信息解析失败，请检查格式是否正确。")
            except Exception as e:
                logger.error(f"解析课程信息失败: {str(e)}")
                await event.reply("抱歉，课程信息解析失败，请检查格式是否正确。")
        
        return MessageEventResult(handled=True)

    def format_course_info(self, course_info):
        """格式化课程信息"""
        msg = "【课程信息】\n\n"
        
        # 基本信息
        if "basic_info" in course_info:
            msg += "📚 基本信息\n"
            for key, value in course_info["basic_info"].items():
                if value:
                    msg += f"• {key}：{value}\n"
            msg += "\n"
        
        # 课程详情
        if "courses" in course_info:
            msg += "🗓️ 课程详情\n"
            for course in course_info["courses"]:
                msg += f"\n星期{course['day']}\n"
                msg += f"上课时间：{course['time']}\n"
                msg += f"课程名称：{course['name']}\n"
                msg += f"教师：{course['teacher']}\n"
                msg += f"上课地点：{course['location']}\n"
                msg += f"周次：{course['weeks']}\n"
        
        return msg

    async def reminder_loop(self):
        """提醒循环"""
        while True:
            try:
                now = datetime.datetime.now()
                
                # 检查当前课程
                for user_id, courses in self.course_data.items():
                    if not self.reminder_status.get(user_id, False):
                        continue
                    
                    current_courses = self.get_current_courses(user_id)
                    if current_courses:
                        for course in current_courses:
                            msg = "【课程上课提醒】\n"
                            msg += f"同学你好，待会有课哦\n"
                            msg += f"上课时间：{course['time']}\n"
                            msg += f"课程名称：{course['name']}\n"
                            msg += f"教师：{course['teacher']}\n"
                            msg += f"上课地点：{course['location']}\n"
                            
                            try:
                                await self.context.send_message(user_id, msg)
                            except Exception as e:
                                logger.error(f"发送课程提醒失败: {str(e)}")
                
                await asyncio.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"提醒循环出错: {str(e)}")
                await asyncio.sleep(60)

    async def daily_notification_task(self):
        """每日通知任务"""
        while True:
            try:
                # 计算下次运行时间
                now = datetime.datetime.now()
                next_run = parser.parse(self.daily_notification_time)
                if next_run <= now:
                    next_run += datetime.timedelta(days=1)
                
                # 等待到指定时间
                wait_seconds = (next_run - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                # 发送通知
                for user_id in self.course_data:
                    if self.reminder_status.get(user_id, True):
                        courses = self.get_tomorrow_courses(user_id)
                        if courses:
                            msg = "【明日课程提醒】\n"
                            for course in courses:
                                msg += f"• {course['name']} ({course['time']})\n"
                                msg += f"  地点：{course['location']}\n"
                                msg += f"  教师：{course['teacher']}\n"
                            
                            msg += "\n是否开启明日课程提醒？回复"确认"开启，回复"取消"关闭。"
                            self.confirmation_status[user_id] = True
                            await self.context.send_message(user_id, msg)
                
            except Exception as e:
                logger.error(f"每日通知任务出错: {str(e)}")
                await asyncio.sleep(60)

    def get_current_courses(self, user_id):
        """获取当前课程"""
        if user_id not in self.course_data:
            return []
        
        now = datetime.datetime.now()
        current_week = self.get_current_week()
        current_day = now.weekday() + 1  # 1-7
        current_time = now.strftime("%H:%M")
        
        courses = []
        for course in self.course_data[user_id].get("courses", []):
            if (course["day"] == current_day and 
                current_week in self.parse_weeks(course["weeks"]) and
                self.is_time_between(current_time, course["time"], self.reminder_time)):
                courses.append(course)
        
        return courses

    def get_tomorrow_courses(self, user_id):
        """获取明日课程"""
        if user_id not in self.course_data:
            return []
        
        tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
        current_week = self.get_current_week()
        tomorrow_day = tomorrow.weekday() + 1  # 1-7
        
        courses = []
        for course in self.course_data[user_id].get("courses", []):
            if (course["day"] == tomorrow_day and 
                current_week in self.parse_weeks(course["weeks"])):
                courses.append(course)
        
        return courses

    def get_current_week(self):
        """获取当前周次"""
        if not self.semester_config:
            return 1
        
        start_date = parser.parse(self.semester_config.get("start_date", ""))
        if not start_date:
            return 1
        
        now = datetime.datetime.now()
        week_diff = (now - start_date).days // 7 + 1
        return max(1, min(week_diff, self.semester_config.get("total_weeks", 16)))

    def parse_weeks(self, weeks_str):
        """解析周次字符串"""
        weeks = set()
        for part in weeks_str.split(","):
            if "-" in part:
                start, end = map(int, part.split("-"))
                weeks.update(range(start, end + 1))
            else:
                weeks.add(int(part))
        return weeks

    def is_time_between(self, current_time, course_time, minutes_before):
        """检查是否在课程时间前指定分钟"""
        try:
            current = parser.parse(current_time)
            course_start = parser.parse(course_time.split("-")[0])
            reminder_time = course_start - datetime.timedelta(minutes=minutes_before)
            
            return current >= reminder_time and current <= course_start
        except:
            return False

    @filter.command("test_reminder")
    async def test_reminder(self, event: AstrMessageEvent) -> MessageEventResult:
        """测试提醒功能"""
        user_id = event.user_id
        
        if user_id not in self.course_data:
            await event.reply("您还没有设置课程信息。")
            return MessageEventResult(handled=True)
        
        # 发送测试提醒
        msg = "【课程提醒测试】\n"
        msg += "上课时间：第1-2节（08:00-09:40）\n"
        msg += "课程名称：如何找到富婆\n"
        msg += "教师：飘逸\n"
        msg += "上课地点：150123"
        
        await event.reply(msg)
        return MessageEventResult(handled=True)

    def terminate(self):
        """插件终止时的清理工作"""
        # 取消所有提醒任务
        for task in self.reminder_tasks.values():
            task.cancel()
        self.reminder_tasks.clear()
        
        # 保存数据
        self.save_data()

    def backup_data(self):
        """备份数据"""
        try:
            backup_dir = os.path.join(self.data_dir, "backup")
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"backup_{timestamp}")
            os.makedirs(backup_path, exist_ok=True)
            
            # 复制数据文件
            for filename in ["course_data.json", "reminder_status.json", "semester_config.json"]:
                src = os.path.join(self.data_dir, filename)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(backup_path, filename))
            
            logger.info(f"数据备份成功: {backup_path}")
        except Exception as e:
            logger.error(f"数据备份失败: {str(e)}")

    @filter.command("set_semester")
    async def set_semester(self, event: AstrMessageEvent, start_date: str, total_weeks: int) -> MessageEventResult:
        """设置学期信息
        
        Args:
            start_date: 学期开始日期，格式：YYYY-MM-DD
            total_weeks: 总周数
        """
        try:
            # 验证日期格式
            start = parser.parse(start_date)
            
            # 保存学期配置
            self.semester_config = {
                "start_date": start_date,
                "total_weeks": total_weeks
            }
            self.save_data()
            
            await event.reply(f"学期信息设置成功！\n开始日期：{start_date}\n总周数：{total_weeks}")
        except Exception as e:
            logger.error(f"设置学期信息失败: {str(e)}")
            await event.reply("设置学期信息失败，请检查日期格式是否正确（YYYY-MM-DD）。")

    @filter.command("list_courses")
    async def list_courses(self, event: AstrMessageEvent) -> MessageEventResult:
        """列出当前课程表"""
        user_id = event.user_id
        
        if user_id not in self.course_data:
            await event.reply("您还没有设置课程信息。")
            return MessageEventResult(handled=True)
        
        msg = self.format_course_info(self.course_data[user_id])
        await event.reply(msg)
        return MessageEventResult(handled=True)

    @filter.command("clear_courses")
    async def clear_courses(self, event: AstrMessageEvent) -> MessageEventResult:
        """清除课程信息"""
        user_id = event.user_id
        
        if user_id in self.course_data:
            del self.course_data[user_id]
            self.save_data()
            await event.reply("课程信息已清除。")
        else:
            await event.reply("您还没有设置课程信息。")
        
        return MessageEventResult(handled=True)

    @filter.command("toggle_reminder")
    async def toggle_reminder(self, event: AstrMessageEvent) -> MessageEventResult:
        """开启/关闭课程提醒"""
        user_id = event.user_id
        
        if user_id not in self.course_data:
            await event.reply("您还没有设置课程信息。")
            return MessageEventResult(handled=True)
        
        current_status = self.reminder_status.get(user_id, False)
        self.reminder_status[user_id] = not current_status
        self.save_data()
        
        status_text = "开启" if not current_status else "关闭"
        await event.reply(f"课程提醒已{status_text}。")
        return MessageEventResult(handled=True) 