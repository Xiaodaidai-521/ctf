import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','ctf_backend.settings'); django.setup()
from student_profiles.models import StudentProfile, LearningPersona
from users.models import CTFUser

user = CTFUser.objects.get(id=40)
profile = StudentProfile.objects.get(user=user)
persona = profile.persona

profile.learning_goals = '系统掌握Web安全攻防全链路，深入理解密码学算法，逐步攻克二进制安全领域，力争一年内达到CTF中级选手水平'
profile.save()

persona.persona_traits = {'strength':['web','crypto'],'weakness':['pwn'],'style':'hands_on','learning_velocity':'快速'}
persona.save()

print('Fixed!')
print('goals:', profile.learning_goals[:60])
print('velocity:', persona.persona_traits.get('learning_velocity'))
