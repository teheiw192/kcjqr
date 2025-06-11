import datetime
import json
import os
import asyncio
from dateutil import parser
from nonebot import on_message
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.typing import T_State
from nonebot import get_driver
from nonebot import require

# 获取配置
driver = get_driver()
plugin_config = driver.config

# 创建数据目录
os.makedirs("data/kcjqr", exist_ok=True)

# 课程提醒插件
class CourseReminderPlugin:
    def __init__(self):
        self.user_courses = {}  # 用户课程数据
        self.reminder_tasks = {}  # 提醒任务
        self.semester_config = None  # 学期配置
        self.reminder_time = 30  # 默认提醒时间（分钟）
        self.daily_notification_time = "23:00"  # 默认每日通知时间
        
        # 加载配置
        if hasattr(plugin_config, "reminder_time"):
            self.reminder_time = plugin_config.reminder_time
        if hasattr(plugin_config, "daily_notification_time"):
            self.daily_notification_time = plugin_config.daily_notification_time
        
        # 加载数据
        self.load_data()
        
        # 启动每日通知任务
        self.start_daily_notification()
    
    def load_data(self):
        """加载数据"""
        try:
            # 加载课程数据
            if os.path.exists("data/kcjqr/courses.json"):
                with open("data/kcjqr/courses.json", "r", encoding="utf-8") as f:
                    self.user_courses = json.load(f)
            
            # 加载提醒状态
            if os.path.exists("data/kcjqr/reminder_status.json"):
                with open("data/kcjqr/reminder_status.json", "r", encoding="utf-8") as f:
                    reminder_status = json.load(f)
                    for user_id, status in reminder_status.items():
                        if user_id in self.user_courses:
                            self.user_courses[user_id]["reminder_enabled"] = status
            
            # 加载学期配置
            if os.path.exists("data/kcjqr/semester_config.json"):
                with open("data/kcjqr/semester_config.json", "r", encoding="utf-8") as f:
                    self.semester_config = json.load(f)
        except Exception as e:
            print(f"加载数据失败: {e}")
    
    def save_data(self):
        """保存数据"""
        try:
            # 保存课程数据
            with open("data/kcjqr/courses.json", "w", encoding="utf-8") as f:
                json.dump(self.user_courses, f, ensure_ascii=False, indent=2)
            
            # 保存提醒状态
            reminder_status = {
                user_id: data.get("reminder_enabled", False)
                for user_id, data in self.user_courses.items()
            }
            with open("data/kcjqr/reminder_status.json", "w", encoding="utf-8") as f:
                json.dump(reminder_status, f, ensure_ascii=False, indent=2)
            
            # 保存学期配置
            if self.semester_config:
                with open("data/kcjqr/semester_config.json", "w", encoding="utf-8") as f:
                    json.dump(self.semester_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存数据失败: {e}")
    
    def parse_course_info(self, text: str) -> dict:
        """解析课程信息"""
        try:
            lines = text.strip().split("\n")
            course_info = {
                "basic_info": {},
                "courses": []
            }
            
            # 解析基本信息
            for line in lines:
                if "学期开始日期" in line:
                    course_info["basic_info"]["start_date"] = line.split("：")[1].strip()
                elif "总周数" in line:
                    course_info["basic_info"]["total_weeks"] = int(line.split("：")[1].strip())
            
            # 解析课程信息
            current_course = None
            for line in lines:
                if "第" in line and "周" in line and "星期" in line:
                    if current_course:
                        course_info["courses"].append(current_course)
                    
                    parts = line.split()
                    week = int(parts[0][1:-1])
                    weekday = "一二三四五六日".index(parts[1][2:]) + 1
                    period = int(parts[2][1:-1])
                    name = parts[3]
                    
                    current_course = {
                        "week": week,
                        "weekday": weekday,
                        "period": period,
                        "name": name,
                        "location": "",
                        "teacher": ""
                    }
                elif current_course:
                    if "地点" in line:
                        current_course["location"] = line.split("：")[1].strip()
                    elif "教师" in line:
                        current_course["teacher"] = line.split("：")[1].strip()
            
            if current_course:
                course_info["courses"].append(current_course)
            
            return course_info
        except Exception as e:
            print(f"解析课程信息失败: {e}")
            return None
    
    def check_course_conflicts(self, courses: list) -> list:
        """检查课程冲突"""
        conflicts = []
        for i in range(len(courses)):
            for j in range(i + 1, len(courses)):
                c1, c2 = courses[i], courses[j]
                if (c1["week"] == c2["week"] and 
                    c1["weekday"] == c2["weekday"] and 
                    c1["period"] == c2["period"]):
                    conflicts.append((c1, c2))
        return conflicts
    
    def backup_data(self):
        """备份数据"""
        try:
            backup_dir = "data/kcjqr/backup"
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"backup_{timestamp}")
            os.makedirs(backup_path, exist_ok=True)
            
            # 备份课程数据
            if os.path.exists("data/kcjqr/courses.json"):
                with open("data/kcjqr/courses.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                with open(os.path.join(backup_path, "courses.json"), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 备份提醒状态
            if os.path.exists("data/kcjqr/reminder_status.json"):
                with open("data/kcjqr/reminder_status.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                with open(os.path.join(backup_path, "reminder_status.json"), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 备份学期配置
            if os.path.exists("data/kcjqr/semester_config.json"):
                with open("data/kcjqr/semester_config.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                with open(os.path.join(backup_path, "semester_config.json"), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"备份数据失败: {e}")
            return False
    
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
                # 计算课程开始和结束时间
                start_minutes = (course["period"] - 1) * 45
                end_minutes = course["period"] * 45
                course_start = datetime.time(8, 0, 0) + datetime.timedelta(minutes=start_minutes)
                course_end = datetime.time(8, 0, 0) + datetime.timedelta(minutes=end_minutes)
                
                # 计算提醒时间
                reminder_datetime = datetime.datetime.combine(datetime.date.today(), course_start) - \
                                  datetime.timedelta(minutes=self.reminder_time)
                reminder_time = reminder_datetime.time()
                
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
                # 计算课程开始和结束时间
                start_minutes = (course["period"] - 1) * 45
                end_minutes = course["period"] * 45
                course_start = datetime.time(8, 0, 0) + datetime.timedelta(minutes=start_minutes)
                course_end = datetime.time(8, 0, 0) + datetime.timedelta(minutes=end_minutes)
                course["time"] = f"{course_start.strftime('%H:%M')}-{course_end.strftime('%H:%M')}"
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
            # 计算课程时间
            start_minutes = (course["period"] - 1) * 45
            end_minutes = course["period"] * 45
            course_start = datetime.time(8, 0, 0) + datetime.timedelta(minutes=start_minutes)
            course_end = datetime.time(8, 0, 0) + datetime.timedelta(minutes=end_minutes)
            course_time = f"{course_start.strftime('%H:%M')}-{course_end.strftime('%H:%M')}"
            
            msg += f"第{course['week']}周 星期{'一二三四五六日'[course['weekday']-1]} "
            msg += f"第{course['period']}节 {course['name']}\n"
            msg += f"时间：{course_time}\n"
            msg += f"地点：{course['location']}\n"
            msg += f"教师：{course['teacher']}\n\n"
        
        return msg
    
    async def send_reminder(self, bot: Bot, user_id: str, course: dict):
        """发送提醒"""
        msg = f"课程提醒：\n{course['name']}\n"
        msg += f"时间：{course['time']}\n"
        msg += f"地点：{course['location']}\n"
        msg += f"教师：{course['teacher']}"
        
        await bot.send_private_msg(user_id=int(user_id), message=msg)
    
    async def reminder_task(self, bot: Bot, user_id: str):
        """提醒任务"""
        while True:
            try:
                if user_id in self.user_courses and self.user_courses[user_id].get("reminder_enabled", False):
                    courses = self.user_courses[user_id]
                    current_courses = self.get_current_courses(courses)
                    
                    for course in current_courses:
                        await self.send_reminder(bot, user_id, course)
                
                await asyncio.sleep(60)  # 每分钟检查一次
            except Exception as e:
                print(f"提醒任务出错: {e}")
                await asyncio.sleep(60)
    
    async def daily_notification_task(self, bot: Bot):
        """每日通知任务"""
        while True:
            try:
                now = datetime.datetime.now()
                target_time = datetime.datetime.strptime(self.daily_notification_time, "%H:%M").time()
                target_datetime = datetime.datetime.combine(now.date(), target_time)
                
                if now.time() > target_time:
                    target_datetime += datetime.timedelta(days=1)
                
                wait_seconds = (target_datetime - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                for user_id, courses in self.user_courses.items():
                    if courses.get("reminder_enabled", False):
                        tomorrow_courses = self.get_tomorrow_courses(courses)
                        if tomorrow_courses:
                            msg = "明日课程提醒：\n"
                            for course in tomorrow_courses:
                                msg += f"\n{course['name']}\n"
                                msg += f"时间：{course['time']}\n"
                                msg += f"地点：{course['location']}\n"
                                msg += f"教师：{course['teacher']}\n"
                            
                            await bot.send_private_msg(user_id=int(user_id), message=msg)
                
                await asyncio.sleep(60)  # 等待一分钟，避免重复发送
            except Exception as e:
                print(f"每日通知任务出错: {e}")
                await asyncio.sleep(60)
    
    def start_daily_notification(self):
        """启动每日通知任务"""
        bot = get_driver().bots[list(get_driver().bots.keys())[0]]
        asyncio.create_task(self.daily_notification_task(bot))
    
    def terminate(self):
        """终止插件"""
        # 保存数据
        self.save_data()
        
        # 取消所有任务
        for task in self.reminder_tasks.values():
            task.cancel()

# 创建插件实例
plugin = CourseReminderPlugin()

# 注册消息处理器
course_handler = on_message(rule=to_me(), priority=5)

@course_handler.handle()
async def handle_course(bot: Bot, event: Event, state: T_State):
    """处理课程消息"""
    user_id = str(event.get_user_id())
    
    # 处理图片或文件
    if event.get_message().has("image") or event.get_message().has("file"):
        await course_handler.finish("请使用文字格式发送课程信息，或使用其他AI识别图片/文件中的课程信息。")
        return
    
    # 处理文本消息
    text = event.get_message().extract_plain_text().strip()
    
    # 处理命令
    if text.startswith("/"):
        cmd = text[1:].split()
        if not cmd:
            await course_handler.finish("请输入有效的命令。")
            return
        
        if cmd[0] == "help":
            msg = "课程提醒插件使用说明：\n"
            msg += "1. 发送课程信息（文字格式）\n"
            msg += "2. 确认课程信息\n"
            msg += "3. 开启/关闭提醒\n"
            msg += "4. 查看课程信息\n"
            msg += "5. 测试提醒功能\n"
            await course_handler.finish(msg)
            return
        
        if cmd[0] == "set_semester":
            if len(cmd) != 3:
                await course_handler.finish("请使用正确的格式：/set_semester <开始日期> <总周数>")
                return
            
            try:
                start_date = parser.parse(cmd[1])
                total_weeks = int(cmd[2])
                
                plugin.semester_config = {
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "total_weeks": total_weeks
                }
                plugin.save_data()
                
                await course_handler.finish(f"学期信息设置成功：\n开始日期：{cmd[1]}\n总周数：{total_weeks}")
            except Exception as e:
                await course_handler.finish(f"设置学期信息失败：{e}")
            return
        
        if cmd[0] == "enable_reminder":
            if user_id not in plugin.user_courses:
                await course_handler.finish("请先发送课程信息。")
                return
            
            plugin.user_courses[user_id]["reminder_enabled"] = True
            plugin.save_data()
            
            # 启动提醒任务
            if user_id not in plugin.reminder_tasks:
                bot = get_driver().bots[list(get_driver().bots.keys())[0]]
                plugin.reminder_tasks[user_id] = asyncio.create_task(
                    plugin.reminder_task(bot, user_id)
                )
            
            await course_handler.finish("课程提醒已开启。")
            return
        
        if cmd[0] == "disable_reminder":
            if user_id not in plugin.user_courses:
                await course_handler.finish("请先发送课程信息。")
                return
            
            plugin.user_courses[user_id]["reminder_enabled"] = False
            plugin.save_data()
            
            # 取消提醒任务
            if user_id in plugin.reminder_tasks:
                plugin.reminder_tasks[user_id].cancel()
                del plugin.reminder_tasks[user_id]
            
            await course_handler.finish("课程提醒已关闭。")
            return
        
        if cmd[0] == "show_courses":
            if user_id not in plugin.user_courses:
                await course_handler.finish("请先发送课程信息。")
                return
            
            msg = plugin.format_course_info(plugin.user_courses[user_id])
            await course_handler.finish(msg)
            return
        
        if cmd[0] == "test_reminder":
            if user_id not in plugin.user_courses:
                await course_handler.finish("请先发送课程信息。")
                return
            
            courses = plugin.user_courses[user_id]
            current_courses = plugin.get_current_courses(courses)
            
            if not current_courses:
                await course_handler.finish("当前没有课程。")
                return
            
            for course in current_courses:
                await plugin.send_reminder(bot, user_id, course)
            
            await course_handler.finish("测试提醒已发送。")
            return
        
        await course_handler.finish("未知命令。")
        return
    
    # 解析课程信息
    course_info = plugin.parse_course_info(text)
    if not course_info:
        await course_handler.finish("解析课程信息失败，请检查格式是否正确。")
        return
    
    # 检查课程冲突
    conflicts = plugin.check_course_conflicts(course_info["courses"])
    if conflicts:
        msg = "发现课程冲突：\n"
        for c1, c2 in conflicts:
            msg += f"\n{c1['name']} 与 {c2['name']} 在"
            msg += f"第{c1['week']}周 星期{'一二三四五六日'[c1['weekday']-1]} "
            msg += f"第{c1['period']}节 冲突\n"
        await course_handler.finish(msg)
        return
    
    # 保存课程信息
    plugin.user_courses[user_id] = course_info
    plugin.save_data()
    
    # 显示课程信息
    msg = "课程信息已保存：\n"
    msg += plugin.format_course_info(course_info)
    msg += "\n使用 /enable_reminder 开启提醒功能。"
    await course_handler.finish(msg)

# 注册终止函数
@driver.on_shutdown
async def shutdown():
    plugin.terminate() 