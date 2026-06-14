"""
更新用户角色数据的脚本
运行命令: python manage.py shell < update_user_roles.py
"""

from users.models import CTFUser

# 将管理员用户设置为 admin 角色
admin_users = CTFUser.objects.filter(username='admin')
admin_users.update(role='admin')

# 将其他用户设置为 student 角色
student_users = CTFUser.objects.filter(role__isnull=True)
student_users.update(role='student')

print("用户角色更新完成！")
print(f"管理员用户: {admin_users.count()} 个")
print(f"学生用户: {student_users.count()} 个")

# 显示所有用户
print("\n用户列表:")
for user in CTFUser.objects.all():
    print(f"  {user.username} - {user.get_role_display()}")
