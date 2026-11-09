from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import CTFUser
from data_security.adapters.persistence.fields import field_storage_enabled


class UserSerializer(serializers.ModelSerializer):
    """用户序列化器"""
    solved_count = serializers.SerializerMethodField()
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    avatar_url = serializers.SerializerMethodField()
    can_manage_catalog = serializers.BooleanField(read_only=True)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    old_password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = CTFUser
        fields = ['id', 'username', 'nickname', 'email', 'role', 'role_display',
                 'score', 'points', 'solved_count', 'team', 'class_name', 'student_id',
                 'bio', 'avatar', 'avatar_url', 'created_at',
                 'is_course_owner', 'can_manage_catalog', 'password', 'old_password']
        read_only_fields = ['id', 'role', 'score', 'points', 'created_at',
                            'is_course_owner', 'can_manage_catalog']

    def validate(self, attrs):
        if 'password' in attrs:
            if not self.instance.check_password(attrs.get('old_password', '')):
                raise serializers.ValidationError({'old_password': '原密码错误'})
            candidate = CTFUser(username=attrs.get('username', self.instance.username),
                                email=attrs['email'] if 'email' in attrs else self.instance.read_protected('email'),
                                first_name=self.instance.first_name,
                                last_name=self.instance.last_name)
            validate_password(attrs['password'], user=candidate)
        return attrs

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        validated_data.pop('old_password', None)
        if password is not None:
            instance.set_password(password)
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if field_storage_enabled() or instance.security_state != 'legacy-v0':
            data['email'] = '[REDACTED]'
        return data

    def get_solved_count(self, obj):
        return obj.get_solved_challenges_count()

    def get_avatar_url(self, obj):
        if obj.avatar:
            return obj.avatar.url
        return None


class UserRegisterSerializer(serializers.ModelSerializer):
    """用户注册序列化器"""
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if field_storage_enabled() or getattr(instance, 'security_state', 'legacy-v0') != 'legacy-v0':
            data['email'] = '[REDACTED]'
        return data

    password = serializers.CharField(write_only=True, required=True, trim_whitespace=False,
                                     style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, trim_whitespace=False,
                                     style={'input_type': 'password'})

    class Meta:
        model = CTFUser
        fields = ['username', 'password', 'password2', 'email', 'nickname',
                 'team', 'class_name', 'student_id', 'enrollment_year']

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "密码不匹配"})
        candidate = CTFUser(**{key: value for key, value in attrs.items()
                               if key not in ('password', 'password2')})
        validate_password(attrs['password'], user=candidate)
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        validated_data['role'] = 'student'
        user = CTFUser.objects.create_user(**validated_data)
        return user


class AdminUserCreateSerializer(serializers.ModelSerializer):
    """管理员创建用户序列化器"""
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if field_storage_enabled() or getattr(instance, 'security_state', 'legacy-v0') != 'legacy-v0':
            data['email'] = '[REDACTED]'
        return data

    password = serializers.CharField(write_only=True, required=True, trim_whitespace=False,
                                     style={'input_type': 'password'})

    class Meta:
        model = CTFUser
        fields = ['username', 'password', 'email', 'nickname', 'role',
                 'team', 'class_name', 'student_id', 'enrollment_year']

    def validate(self, attrs):
        candidate = CTFUser(**{key: value for key, value in attrs.items() if key != 'password'})
        validate_password(attrs['password'], user=candidate)
        return attrs

    def create(self, validated_data):
        return CTFUser.objects.create_user(**validated_data)


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """管理员更新用户序列化器"""
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if field_storage_enabled() or getattr(instance, 'security_state', 'legacy-v0') != 'legacy-v0':
            data['email'] = '[REDACTED]'
        return data

    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = CTFUser
        fields = ['nickname', 'email', 'role', 'team', 'class_name',
                 'student_id', 'enrollment_year', 'bio', 'password']

    def validate(self, attrs):
        if 'password' in attrs:
            candidate = CTFUser(username=self.instance.username,
                                email=attrs['email'] if 'email' in attrs else self.instance.read_protected('email'),
                                first_name=self.instance.first_name,
                                last_name=self.instance.last_name)
            validate_password(attrs['password'], user=candidate)
        return attrs

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password is not None:
            instance.set_password(password)
        return super().update(instance, validated_data)


class UserLoginSerializer(serializers.Serializer):
    """用户登录序列化器"""
    username = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True, trim_whitespace=False,
                                     style={'input_type': 'password'})


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
