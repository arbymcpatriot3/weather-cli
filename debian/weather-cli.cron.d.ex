#
# Regular cron jobs for the weather-cli package.
#
0 4	* * *	root	[ -x /usr/bin/weather-cli_maintenance ] && /usr/bin/weather-cli_maintenance
