# -*- coding: utf-8 -*-
"""spb-mail 版本发布邮件 固定收件人/抄送人配置。

固化 JZJY(集中交易) 与 CSZX(参数中心) 版本发布邮件的收件人(To)与抄送(Cc)名单，
供保存草稿/发送时统一引用，避免每次手抄遗漏。

变更记录：
2026-10-26  CSZX 收件人新增 姚松明（系统运行部）。
            注：姚松明暂未登记邮箱，存草稿时以姓名下发，由 Coremail 企业通讯录匹配；
            拿到邮箱后请回填为 "姚松明" <xxx@gtht.com> 格式。
"""

RECIPIENTS = {
    "JZJY": {
        "recipients": [
            '"李萍萍" <lipingping@gtht.com>',
            '"陈浩宇" <chenhaoyu@gtht.com>',
            '"陈曦" <chenxi10@gtht.com>',
            '"1791894837" <1791894837@qq.com>',
            '"高健" <gaojian2@gtht.com>',
            '"shenss" <shenss@guoliansh.com>',
            '"贺元成" <heyuancheng@gtht.com>',
            '"张子安" <zhangzian@gtht.com>',
            '"陈紫菡" <chenzihan@gtht.com>',
            '"常丽" <changli@gtht.com>',
            '"张博闻" <zhangbowen@gtht.com>',
        ],
        "cc": [
            '"苏清玲" <suqingling@gtht.com>',
            '"李鹤晨" <lihechen@gtht.com>',
            '"张康" <zhangkang2@gtht.com>',
        ],
    },
    "CSZX": {
        "recipients": [
            '"万鑫明" <wanxinming@gtht.com>',
            '"白淋" <bailin2@gtht.com>',
            '"李龙龙" <lilonglong@gtht.com>',
            '"张颖" <zhangying12@gtht.com>',
            '"丁伟" <dingwei2@gtht.com>',
            '"夏添" <xiatian2@gtht.com>',
            '"15021289638" <15021289638@163.com>',
            '"高健" <gaojian2@gtht.com>',
            '"陈紫菡" <chenzihan@gtht.com>',
            # 2026-10-26 固定收件人（系统运行部）；邮箱待回填
            "姚松明",
        ],
        "cc": [
            '"鄂文博" <ewenbo@gtht.com>',
            '"程菲" <chengfei@gtht.com>',
            '"苏清玲" <suqingling@gtht.com>',
            '"张康" <zhangkang2@gtht.com>',
        ],
    },
}
