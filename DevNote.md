共享服务器 unity 

镜像仓库凭证设置
在拉取私有镜像或者上传镜像前，需要 docker login 输入您的凭证信息
仓库账号
agenticfac1
仓库密码
重置密码
请注意妥善保管。如果遗失，可以重置密码。

1. 登录镜像仓库
在电脑终端中输入访问凭证（命令如下），登录镜像仓库
docker login harbor.suanleme.cn --username=agenticfac1

查看详细的镜像仓库使用说明 →
2. 上传镜像到仓库
按照以下步骤将您的镜像推送到仓库
docker tag [ImageId] harbor.suanleme.cn/agenticfac1/[镜像名称]:[镜像版本号]

docker push harbor.suanleme.cn/agenticfac1/[镜像名称]:[镜像版本号]

请将命令中的以下参数替换为实际值：

[ImageId]：本地镜像的 ID 或名称
[镜像名称]：您想要使用的镜像名称
[镜像版本号]：镜像的版本标签，如 latest、v1.0.0 等
示例：
# 查看本地镜像列表 
docker images 
REPOSITORY                            TAG         IMAGE ID          CREATED VIRTUAL      SIZE 
harbor.suanleme.cn/library/nginx      latest      ad4b31aa2de6      7 days ago           37.89 MB 

# 使用 docker tag 命令重命名镜像 
docker tag ad4b31aa2de6 harbor.suanleme.cn/agenticfac1/nginx:0.7 

# 使用 docker push 命令推送镜像 

docker push harbor.suanleme.cn/agenticfac1/nginx:0.7
