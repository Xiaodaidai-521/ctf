from rest_framework import serializers
from .models import CTFUser


class UserSerializer(serializers.ModelSerializer):
    """用户序列化器"""
    solved_count = serializers.SerializerMethodField()
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = CTFUser
        fields = ['id', 'username', 'nickname', 'email', 'role', 'role_display',
                 'score', 'points', 'solved_count', 'team', 'class_name', 'student_id',
                 'bio', 'avatar', 'avatar_url', 'created_at']
        read_only_fields = ['id', 'role', 'score', 'points', 'created_at']

    def get_solved_count(self, obj):
        return obj.get_solved_challenges_count()

    def get_avatar_url(self, obj):
        if obj.avatar:
            return obj.avatar.url
        return None


class UserRegisterSerializer(serializers.ModelSerializer):
    """用户注册序列化器"""
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = CTFUser
        fields = ['username', 'password', 'password2', 'email', 'nickname',
                 'team', 'class_name', 'student_id', 'enrollment_year']

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "密码不匹配"})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        validated_data['role'] = 'student'
        user = CTFUser.objects.create_user(**validated_data)
        return user


class AdminUserCreateSerializer(serializers.ModelSerializer):
    """管理员创建用户序列化器"""
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = CTFUser
        fields = ['username', 'password', 'email', 'nickname', 'role',
                 'team', 'class_name', 'student_id', 'enrollment_year']

    def create(self, validated_data):
        return CTFUser.objects.create_user(**validated_data)


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """管理员更新用户序列化器"""

    class Meta:
        model = CTFUser
        fields = ['nickname', 'email', 'role', 'team', 'class_name',
                 'student_id', 'enrollment_year', 'bio']


class UserLoginSerializer(serializers.Serializer):
    """用户登录序列化器"""
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, style={'input_type': 'password'})


class LeaderboardSerializer(serializers.ModelSerializer):
    """排行榜序列化器"""
    rank = serializers.SerializerMethodField()
    solved_count = serializers.SerializerMethodField()

    class Meta:
        model = CTFUser
        fields = ['rank', 'username', 'nickname', 'team', 'score', 'solved_count']

    def get_rank(self, obj):
        """获取排名"""
        return self.context.get('rank', 0)

    def get_solved_count(self, obj):
        return obj.get_solved_challenges_count()
