"""
ZMC 告警数据模型

定义从 Oracle 数据库读取的告警数据结构。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ZMCAlarm(BaseModel):
    """ZMC 告警完整信息模型"""

    # ========== 告警事件基础信息 ==========
    event_inst_id: int = Field(..., description="告警事件唯一ID")
    event_time: Optional[datetime] = Field(None, description="告警发生时间")
    create_date: Optional[datetime] = Field(None, description="记录创建时间")
    alarm_code: int = Field(..., description="告警码")
    alarm_level: Optional[str] = Field(None, description="告警级别: 1-严重, 2-重要, 3-次要, 4-警告")
    reset_flag: str = Field(..., description="恢复标志: 0-恢复, 1-告警")
    task_type: Optional[str] = Field(None, description="任务类型")
    task_id: Optional[int] = Field(None, description="任务ID")
    res_inst_type: Optional[str] = Field(None, description="资源类型: DEVICE/APP_SERVICE/APP_PROCESS")
    res_inst_id: Optional[int] = Field(None, description="资源实例ID")
    app_env_id: Optional[int] = Field(None, description="应用环境ID")
    detail_info: Optional[str] = Field(None, description="告警详细信息")

    # 扩展字段 DATA_1 ~ DATA_10
    data_1: Optional[str] = Field(None, description="扩展字段1")
    data_2: Optional[str] = Field(None, description="扩展字段2")
    data_3: Optional[str] = Field(None, description="扩展字段3")
    data_4: Optional[str] = Field(None, description="扩展字段4")
    data_5: Optional[str] = Field(None, description="扩展字段5")
    data_6: Optional[str] = Field(None, description="扩展字段6")
    data_7: Optional[str] = Field(None, description="扩展字段7")
    data_8: Optional[str] = Field(None, description="扩展字段8")
    data_9: Optional[str] = Field(None, description="扩展字段9")
    data_10: Optional[str] = Field(None, description="扩展字段10")

    # ========== 告警汇总状态 ==========
    alarm_inst_id: Optional[int] = Field(None, description="告警汇总ID")
    alarm_state: Optional[str] = Field(None, description="告警状态: U/A/M/C")
    reset_date: Optional[datetime] = Field(None, description="自动恢复时间")
    clear_date: Optional[datetime] = Field(None, description="手工清除时间")
    confirm_date: Optional[datetime] = Field(None, description="确认时间")
    total_alarm: Optional[int] = Field(None, description="累计告警次数")
    clear_reason: Optional[str] = Field(None, description="清除原因")

    # ========== 告警码详情 ==========
    alarm_name: Optional[str] = Field(None, description="告警名称")
    alarm_type_code: Optional[str] = Field(None, description="告警类型代码")
    alarm_type_name: Optional[str] = Field(None, description="告警类型名称")
    default_warn_level: Optional[str] = Field(None, description="默认告警级别")
    fault_reason: Optional[str] = Field(None, description="故障原因")
    deal_suggest: Optional[str] = Field(None, description="处理建议")

    # ========== 设备/主机信息 ==========
    device_id: Optional[int] = Field(None, description="设备ID")
    host_name: Optional[str] = Field(None, description="主机名")
    host_ip: Optional[str] = Field(None, description="主机IP地址")
    device_model: Optional[str] = Field(None, description="设备型号")

    # ========== 应用环境信息 ==========
    app_name: Optional[str] = Field(None, description="应用名称")
    app_user: Optional[str] = Field(None, description="应用用户")

    # ========== 业务域信息 ==========
    domain_id: Optional[int] = Field(None, description="业务域ID")
    business_domain: Optional[str] = Field(None, description="业务域名称")
    domain_type: Optional[str] = Field(None, description="域类型代码")
    environment: Optional[str] = Field(None, description="环境类型: Production/Test/DR")

    # ========== 应用服务/进程信息 ==========
    app_service_name: Optional[str] = Field(None, description="应用服务名称")
    service_ip: Optional[str] = Field(None, description="服务IP地址")
    process_name: Optional[str] = Field(None, description="进程名称")

    class Config:
        from_attributes = True

    @property
    def is_recovery(self) -> bool:
        """是否为恢复消息"""
        return self.reset_flag == "0"

    @property
    def is_active(self) -> bool:
        """是否为活跃告警"""
        return self.alarm_state in (None, "U")

    @property
    def is_cleared(self) -> bool:
        """是否已清除/恢复"""
        return self.alarm_state in ("A", "M", "C")

    @property
    def effective_severity(self) -> str:
        """有效告警级别"""
        return self.alarm_level or self.default_warn_level or "3"

    @property
    def effective_host(self) -> str:
        """
        有效主机标识

        格式与 ZMC 前台一致: 主机名@IP (如 pr-ocs02@10.25.177.3)
        """
        if self.host_name and self.host_ip:
            return f"{self.host_name}@{self.host_ip}"
        elif self.host_ip:
            return self.host_ip
        elif self.host_name:
            return self.host_name
        else:
            return f"device_{self.device_id or 'unknown'}"

    @property
    def effective_alert_name(self) -> str:
        """有效告警名称"""
        return self.alarm_name or f"ZMC_ALARM_{self.alarm_code}"

    def get_resolved_time(self) -> Optional[datetime]:
        """获取告警恢复时间"""
        if self.alarm_state == "A":
            return self.reset_date
        elif self.alarm_state in ("M", "C"):
            return self.clear_date or self.confirm_date
        return None


class AlarmSyncStatus(BaseModel):
    """告警同步状态模型"""

    sync_id: Optional[int] = Field(None, description="同步记录ID")
    event_inst_id: int = Field(..., description="告警事件ID")
    alarm_inst_id: Optional[int] = Field(None, description="告警汇总ID")
    sync_status: str = Field(..., description="同步状态: PENDING/FIRING/RESOLVED/SILENCED/ERROR")
    zmc_alarm_state: Optional[str] = Field(None, description="ZMC侧告警状态")
    last_push_time: Optional[datetime] = Field(None, description="最后推送时间")
    push_count: int = Field(default=0, description="推送次数")
    am_fingerprint: Optional[str] = Field(None, description="Alertmanager指纹")
    silence_id: Optional[str] = Field(None, description="静默规则ID")
    error_count: int = Field(default=0, description="错误次数")
    last_error: Optional[str] = Field(None, description="最后错误信息")
    create_time: Optional[datetime] = Field(None, description="创建时间")
    update_time: Optional[datetime] = Field(None, description="更新时间")

    class Config:
        from_attributes = True


class AlarmSyncLog(BaseModel):
    """告警同步日志模型"""

    log_id: Optional[int] = Field(None, description="日志ID")
    sync_batch_id: Optional[str] = Field(None, description="同步批次ID")
    event_inst_id: Optional[int] = Field(None, description="告警事件ID")
    operation: str = Field(..., description="操作类型")
    old_status: Optional[str] = Field(None, description="操作前状态")
    new_status: Optional[str] = Field(None, description="操作后状态")
    request_url: Optional[str] = Field(None, description="请求URL")
    request_method: Optional[str] = Field(None, description="HTTP方法")
    request_payload: Optional[str] = Field(None, description="请求体")
    response_code: Optional[int] = Field(None, description="响应码")
    response_body: Optional[str] = Field(None, description="响应体")
    error_message: Optional[str] = Field(None, description="错误信息")
    duration_ms: Optional[int] = Field(None, description="耗时(毫秒)")
    create_time: Optional[datetime] = Field(None, description="创建时间")

    class Config:
        from_attributes = True


class AlarmStatistics(BaseModel):
    """告警统计信息"""

    sync_status: str = Field(..., description="同步状态")
    alarm_count: int = Field(..., description="告警数量")
    earliest_alarm: Optional[datetime] = Field(None, description="最早告警时间")
    latest_update: Optional[datetime] = Field(None, description="最近更新时间")
    total_pushes: int = Field(default=0, description="总推送次数")
    total_errors: int = Field(default=0, description="总错误次数")
    alarms_with_errors: int = Field(default=0, description="有错误的告警数")

    class Config:
        from_attributes = True
