from django.db import models
from data_security.adapters.persistence.fields import ProtectedModel
from django.db.models import F
from users.models import CTFUser
from challenges.models import Challenge


class Submission(ProtectedModel):
    """提交记录模型"""
    encrypted_fields = ('flag',)
    user = models.ForeignKey(CTFUser, on_delete=models.CASCADE, verbose_name='用户')
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, verbose_name='题目')
    flag = models.CharField(max_length=200, verbose_name='提交的Flag')
    is_correct = models.BooleanField(default=False, verbose_name='是否正确')
    ip_address = models.GenericIPAddressField(verbose_name='IP地址')
    user_agent = models.TextField(verbose_name='用户代理')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='提交时间')

    class Meta:
        verbose_name = '提交记录'
        verbose_name_plural = '提交记录'
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(
            condition=models.Q(security_state='legacy-v0') | models.Q(flag=''),
            name='submission_sealed_flag_no_plaintext')]

    def __str__(self):
        status = '✓' if self.is_correct else '✗'
        return f"{self.user.username} - {self.challenge.title} {status}"

    def save(self, *args, **kwargs):
        was_correct = False
        if self.pk:
            was_correct = Submission.objects.filter(
                pk=self.pk,
                is_correct=True
            ).exists()

        already_solved = Submission.objects.filter(
            user=self.user,
            challenge=self.challenge,
            is_correct=True
        ).exclude(pk=self.pk).exists()

        # 验证Flag
        flag = self.flag if self._state.adding or 'flag' in self._security_dirty else self.read_protected('flag')
        if flag.strip() == self.challenge.read_protected('flag').strip():
            self.is_correct = True
            if not was_correct and not already_solved:
                Challenge.objects.filter(pk=self.challenge.pk).update(
                    solve_count=F('solve_count') + 1
                )
        else:
            self.is_correct = False

        super().save(*args, **kwargs)

        # 如果正确，更新用户分数
        if self.is_correct:
            self.user.update_score()
