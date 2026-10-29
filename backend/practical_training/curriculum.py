"""Original candidate material. Publication still requires course-owner review."""

MATERIAL = {
    'student_material_refs': ['module5:document-access-v1'],
    'withdrawn': False,
    'knowledge': '公开链接不等于公开授权。先判断文档的数据范围，再检查服务端读取路径的身份与权限。'
                 '客户端隐藏链接不能代替服务端拒绝访问。只读取本次个人实验实例内的合成文档。',
    'source_refs': ['OWASP WSTG v4.2 / WSTG-ATHZ-02'],
    'scope': '教学合成数据，不构成生产修复或合规证明。',
}
HINTS = [
    {'level': 1, 'content': '先区分公开资料与内部资料，检查可见链接是否具有服务端访问控制。'},
    {'level': 2, 'content': '授权应发生在服务端读取资源之前，不能仅依赖前端导航是否展示。'},
    {'level': 3, 'content': '检查个人实例中的文档入口，记录哪些资料未登录时也能访问。'},
    {'level': 4, 'content': '在授权实例的公开文档目录中检查内部文档是否被错误公开；不要访问实例之外的目标。'},
]
REPAIR_MATERIAL = {
    'student_material_refs': ['module5:document-policy-lab-v1'], 'withdrawn': False,
    'knowledge': '新场景：合成项目资料库。公开资料可匿名读取；内部资料仅允许同租户成员，'
                 '私有资料仅允许同租户所有者。未知类型默认拒绝。既验证拒绝越权，也验证正常访问。',
    'proposal_schema': {'default': 'deny 或 allow', 'rules': {
        'public': 'public / tenant / owner / deny',
        'internal': 'public / tenant / owner / deny',
        'private': 'public / tenant / owner / deny',
    }},
    'scope': '提交访问控制方案，服务端在固定合成请求上重新执行。不是对 Juice Shop 的在线补丁。',
}
