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

    @filter.message()
    async def on_message(self, event: AstrMessageEvent) -> MessageEventResult:
        """处理消息"""
        user_id = event.user_id
        
        # 检查是否是图片或文件
        if event.message_type in ["image", "file"]:
            await event.reply("请使用其他AI来识别图片或文件中的课程信息。")
            return MessageEventResult(handled=True)
        
        # 处理文本消息
        if event.message_type == "text":
            # 检查是否在等待确认状态
            if user_id in self.confirmation_status:
                if event.content.lower() in ["是", "yes", "y"]:
                    # 保存课程信息
                    self.course_data[user_id] = self.confirmation_status[user_id]
                    self.reminder_status[user_id] = True
                    self.save_data()
                    del self.confirmation_status[user_id]
                    await event.reply("课程信息已保存！\n提醒功能已自动开启。")
                else:
                    del self.confirmation_status[user_id]
                    await event.reply("已取消保存课程信息。")
                return MessageEventResult(handled=True)
            
            # 尝试解析课程信息
            try:
                course_info = self.parse_course_info(event.content)
                if course_info:
                    # 请求用户确认
                    self.confirmation_status[user_id] = course_info
                    msg = self.format_course_info(course_info)
                    await event.reply(f"请确认以下课程信息是否正确？\n\n{msg}\n\n回复"是"确认，其他内容取消。")
                    return MessageEventResult(handled=True)
            except Exception as e:
                logger.error(f"解析课程信息失败: {str(e)}")
        
        return MessageEventResult(handled=False)

    async def reminder_loop(self):
        """提醒循环"""
        while True:
            try:
                now = datetime.datetime.now()
                
                # 检查每个用户的课程
                for user_id, courses in self.course_data.items():
                    if not self.reminder_status.get(user_id, False):
                        continue
                    
                    # 获取当前课程
                    current_courses = self.get_current_courses(courses)
                    if current_courses:
                        # 发送提醒
                        for course in current_courses:
                            msg = f"提醒：{course['name']} 课程即将开始！\n"
                            msg += f"时间：{course['time']}\n"
                            msg += f"地点：{course['location']}\n"
                            msg += f"教师：{course['teacher']}"
                            await self.context.send_message(user_id, msg)
                
                # 等待1分钟
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"提醒循环出错: {str(e)}")
                await asyncio.sleep(60)

    async def daily_notification_task(self):
        """每日通知任务"""
        while True:
            try:
                now = datetime.datetime.now()
                target_time = parser.parse(self.daily_notification_time).time()
                next_run = datetime.datetime.combine(now.date(), target_time)
                
                if now.time() >= target_time:
                    next_run += datetime.timedelta(days=1)
                
                # 等待到目标时间
                await asyncio.sleep((next_run - now).total_seconds())
                
                # 发送每日通知
                for user_id, courses in self.course_data.items():
                    if not self.reminder_status.get(user_id, False):
                        continue
                    
                    tomorrow_courses = self.get_tomorrow_courses(courses)
                    if tomorrow_courses:
                        msg = "明日课程安排：\n\n"
                        for course in tomorrow_courses:
                            msg += f"{course['time']} {course['name']}\n"
                            msg += f"地点：{course['location']}\n"
                            msg += f"教师：{course['teacher']}\n\n"
                        await self.context.send_message(user_id, msg)
            except Exception as e:
                logger.error(f"每日通知任务出错: {str(e)}")
                await asyncio.sleep(60)

    def parse_course_info(self, text: str) -> dict:
        """解析课程信息"""
        # 提取基本信息
        basic_info = {}
        basic_pattern = r"学期开始日期：(\d{4}-\d{2}-\d{2})\n总周数：(\d+)"
        basic_match = re.search(basic_pattern, text)
        if basic_match:
            basic_info["start_date"] = basic_match.group(1)
            basic_info["total_weeks"] = int(basic_match.group(2))
        
        # 提取课程信息
        courses = []
        course_pattern = r"第(\d+)周\s+星期([一二三四五六日])\s+第(\d+)节\s+([^\n]+)\s+([^\n]+)\s+([^\n]+)"
        for match in re.finditer(course_pattern, text):
            week = int(match.group(1))
            weekday = "一二三四五六日".index(match.group(2)) + 1
            period = int(match.group(3))
            name = match.group(4).strip()
            location = match.group(5).strip()
            teacher = match.group(6).strip()
            
            courses.append({
                "week": week,
                "weekday": weekday,
                "period": period,
                "name": name,
                "location": location,
                "teacher": teacher
            })
        
        if not courses:
            return None
        
        return {
            "basic_info": basic_info,
            "courses": courses
        }

    def get_current_courses(self, courses: dict) -> list:
        """获取当前课程"""
        if not self.semester_config:
            return []
        
        now = datetime.datetime.now()
        start_date = parser.parse(self.semester_config["start_date"])
        current_week = ((now - start_date).days // 7) + 1
        
        if current_week > self.semester_config["total_weeks"]:
            return []
        
        current_weekday = now.weekday() + 1
        current_time = now.time()
        
        result = []
        for course in courses["courses"]:
            if course["week"] == current_week and course["weekday"] == current_weekday:
                # 计算课程开始时间
                course_start = datetime.time(8, 0) + datetime.timedelta(minutes=(course["period"] - 1) * 45)
                course_end = datetime.time(8, 0) + datetime.timedelta(minutes=course["period"] * 45)
                
                # 检查是否在提醒时间范围内
                reminder_time = (datetime.datetime.combine(datetime.date.today(), course_start) - 
                               datetime.timedelta(minutes=self.reminder_time)).time()
                
                if reminder_time <= current_time <= course_end:
                    course["time"] = f"{course_start.strftime('%H:%M')}-{course_end.strftime('%H:%M')}"
                    result.append(course)
        
        return result

    def get_tomorrow_courses(self, courses: dict) -> list:
        """获取明日课程"""
        if not self.semester_config:
            return []
        
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)
        start_date = parser.parse(self.semester_config["start_date"])
        current_week = ((tomorrow - start_date).days // 7) + 1
        
        if current_week > self.semester_config["total_weeks"]:
            return []
        
        tomorrow_weekday = tomorrow.weekday() + 1
        
        result = []
        for course in courses["courses"]:
            if course["week"] == current_week and course["weekday"] == tomorrow_weekday:
                result.append(course)
        
        return result

    def format_course_info(self, course_info: dict) -> str:
        """格式化课程信息"""
        msg = ""
        if "basic_info" in course_info:
            msg += f"学期开始日期：{course_info['basic_info']['start_date']}\n"
            msg += f"总周数：{course_info['basic_info']['total_weeks']}\n\n"
        
        msg += "课程信息：\n"
        for course in course_info["courses"]:
            msg += f"第{course['week']}周 星期{'一二三四五六日'[course['weekday']-1]} "
            msg += f"第{course['period']}节 {course['name']}\n"
            msg += f"地点：{course['location']}\n"
            msg += f"教师：{course['teacher']}\n\n"
        
        return msg

    @filter.command("set_semester")
    async def set_semester(self, event: AstrMessageEvent, start_date: str, total_weeks: int) -> MessageEventResult:
        """设置学期信息"""
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
        
        return MessageEventResult(handled=True)

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

    def check_course_conflicts(self, courses: list) -> list:
        """检查课程冲突"""
        conflicts = []
        for i in range(len(courses)):
            for j in range(i + 1, len(courses)):
                if (courses[i]["week"] == courses[j]["week"] and
                    courses[i]["weekday"] == courses[j]["weekday"] and
                    courses[i]["period"] == courses[j]["period"]):
                    conflicts.append((courses[i], courses[j]))
        return conflicts

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

    @filter.command("test_reminder")
    async def test_reminder(self, event: AstrMessageEvent) -> MessageEventResult:
        """测试提醒功能"""
        user_id = event.user_id
        
        if user_id not in self.course_data:
            await event.reply("您还没有设置课程信息。")
            return MessageEventResult(handled=True)
        
        if not self.reminder_status.get(user_id, False):
            await event.reply("提醒功能未开启，请先开启提醒功能。")
            return MessageEventResult(handled=True)
        
        # 获取当前课程
        current_courses = self.get_current_courses(self.course_data[user_id])
        if not current_courses:
            await event.reply("当前没有需要提醒的课程。")
            return MessageEventResult(handled=True)
        
        # 发送测试提醒
        for course in current_courses:
            msg = f"测试提醒：{course['name']} 课程即将开始！\n"
            msg += f"时间：{course['time']}\n"
            msg += f"地点：{course['location']}\n"
            msg += f"教师：{course['teacher']}"
            await event.reply(msg)
        
        return MessageEventResult(handled=True)

    def terminate(self):
        """插件终止时调用"""
        # 保存数据
        self.save_data()
        
        # 取消所有任务
        for task in self.reminder_tasks.values():
            task.cancel() 