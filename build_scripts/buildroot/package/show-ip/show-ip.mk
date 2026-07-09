################################################################################
#
# show-ip
#
################################################################################

SHOW_IP_SITE        = $(BR2_EXTERNAL_AD5M_PATH)/package/show-ip/src
SHOW_IP_SITE_METHOD = local

define SHOW_IP_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) -O2 -Wall -Wextra \
		-o $(@D)/show_ip $(@D)/show_ip.c \
		$(TARGET_LDFLAGS)
endef

define SHOW_IP_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/show_ip \
		$(TARGET_DIR)/usr/share/klipper_mod/show_ip
endef

$(eval $(generic-package))
