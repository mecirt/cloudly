# -*- coding: utf-8
#!/usr/bin/env python

import os
import sys
import re
import time
import datetime
import platform
import base64, pickle

import json
import urllib2
import requests
import subprocess

AGENT_VERSION = "0.1"

SECRET = "588-R2G9-13809"
API_SERVER = "127.0.0.1:5000"

HWADDR = subprocess.Popen(["ifconfig","eth0"], stdout=subprocess.PIPE, close_fds=True).communicate()[0]
if not platform.system() == 'Darwin':
	UUID = re.search(r'([0-9A-F]{2}[:-]){5}([0-9A-F]{2})', HWADDR, re.I).group()
else:
	UUID = "devel"

# Required packages:~$ apt-get install kvm qemu-kvm \
#  iptables libvirt0 libvirt-bin virtinst openvpn \
#  bridge-utils hdparm mdadm sasl2-bin pm-utils \
#  python-libvirt python-virtinst python-requests python-bson python-pip

def _get_sys_loadavg():
	
	loadavg=subprocess.Popen(['uptime',], stdout=subprocess.PIPE, close_fds=True).communicate()[0]
	loadavg = re.findall(r"(\d+\.\d{2})", loadavg)

	return loadavg


def _get_sys_uptime():
	
	uptime = subprocess.Popen(['uptime',], stdout=subprocess.PIPE, close_fds=True).communicate()[0]
	uptime = re.findall("[ 0-9:]up[ ](.*)[,][ 0-9]+user", uptime)[0]

	return uptime


def _get_sys_cpu():
	
	top_info = subprocess.Popen(["top","b","n","1"], stdout=subprocess.PIPE, close_fds=True).communicate()[0]

	c=0
	cpu_total = float(0)
	
	for line in top_info.split('\n'):
		if(c==6): pass
		if(c<7): c+=1

		line = str(line).split(' ')[:-6]
		try:
			cpu_process_usage = float(line[-1:][0])
			cpu_total += cpu_process_usage
		except:
			pass
	
	cpu_usage = {
		'cpu_used':round(cpu_total,2),
		'cpu_free':round(float(100-cpu_total),2)
	}

	return cpu_usage


def _get_sys_cpu_info():

	cpu = 0
	cpu_info = {}

	for line in open('/proc/cpuinfo').readlines():

		element = re.findall(r"^(.+)\s+[:][ ](.*)$", line)

		if(element):

			key = element[0][0].replace('\t','').replace(' ','_')
			value = element[0][1]

			try:
				cpu_info['cpu'+str(cpu)][key] = value
			except:
				cpu_info['cpu'+str(cpu)] = {}
				cpu_info['cpu'+str(cpu)][key] = value

		if(len(line)==1): cpu += 1

	return cpu_info


def _get_memory_usage():
	
	memory_info = subprocess.Popen(["cat","/proc/meminfo"], stdout=subprocess.PIPE, close_fds=True).communicate()[0]

	memory_total = ""
	memory_free = ""
	for element in memory_info.split('\n'):
		if("MemTotal" in element): memory_total = element
		if("MemFree" in element): memory_free = element

	try:
		memory_total = long(memory_total.split(' ')[-2:-1][0]) * 1024
		memory_free = long(memory_free.split(' ')[-2:-1][0]) * 1024
		memory_used = long(memory_total-memory_free)
	except:
		memory_total = -1
		memory_free = -1
		memory_used = -1

	memory_usage = {
		'memory_total': memory_total,
		'memory_free': memory_free,
		'memory_used': memory_used,		
		'memory_used_percentage': round(float(memory_used)/float(memory_total)*100,2),
	}
		
	return memory_usage


def _get_ip_address():
	
	ifconfig = subprocess.Popen(["/sbin/ifconfig","eth0"], stdout=subprocess.PIPE, close_fds=True).communicate()[0]
	ip = re.search( r'inet addr:[^\s]+', ifconfig )
	if not platform.system() == 'Darwin':
		ip = ip.group().split(':')[-1]
	else:
		ip = "127.0.0.1"
	return ip
	

def _get_sys_cpu_virtualization():

	virtualization_support = False

	cpuinfo = open('/proc/cpuinfo','rt').readlines()
	for line in cpuinfo:
		
		if("vmx" in line): 
			virtualization_support = True
		if("svm" in line): 
			virtualization_support = True
		
	return virtualization_support


def _get_physical_disks():

	physical_disks = []

	physical_disks_list = subprocess.Popen(["/sbin/fdisk","-l"], stdout=subprocess.PIPE, close_fds=True).communicate()[0]
	physical_disks_list_ = physical_disks_list.split('\n')

	physical_disks_list = []
	for line in physical_disks_list_:

		if('Disk' in line):
			disk = line.split(' ')[1].replace(':','')
			try:
				bsize = long(line.split(' ')[-2:-1][0])
				physical_disks_list.append([disk,bsize])
			except: pass

	for hdd in physical_disks_list:
	
		FNULL = open(os.devnull, 'w')
		disk_info = subprocess.Popen(["/sbin/hdparm","-I",hdd[0],], stderr=FNULL, stdout=subprocess.PIPE, close_fds=True).communicate()[0]
		
		model_number = "n/a"
		serial_number = "n/a"
		firmware_revision = "n/a"
				
		for line in disk_info.split('\n'):
		
			if("Model Number" in line): model_number = line.split(':')[1].replace(' ','')
			if("Serial Number" in line): serial_number = line.split(':')[1].replace(' ','')
			if("Firmware Revision" in line): firmware_revision = line.split(':')[1].replace(' ','')
		

		try: model_number.decode('utf-8')
		except UnicodeDecodeError: model_number = "n/a"

		try: serial_number.decode('utf-8')
		except UnicodeDecodeError: serial_number = "n/a"

		try: firmware_revision.decode('utf-8')
		except UnicodeDecodeError: firmware_revision = "n/a"
				
		disk_info = {
			'device':hdd[0],
			'size':hdd[1],
			'model_number':model_number,
			'serial_number':serial_number,
			'firmware_revision':firmware_revision,
		}
		physical_disks.append(disk_info)
		
	return physical_disks


def _get_disks_usage():

	proc = subprocess.Popen(['/bin/df', '-B 1'], stdout=subprocess.PIPE, close_fds=True)
	df = proc.communicate()[0] 

	try:
		volumes = df.split('\n')
		volumes.pop(0)
		volumes.pop()
	except: return {"error":True,"error_description":"_get_disks_usage"}

	regexp = re.compile(r'([0-9]+)')
	previousVolume = None
	volumeCount = 0
	disks_usage = []
	
	for volume in volumes:
		
		volume = volume.split(None, 10)
		
		if len(volume) == 1:
			previousVolume = volume[0]
			continue
		
		if previousVolume != None:
			volume.insert(0, previousVolume) 
			previousVolume = None
		
		volumeCount = volumeCount + 1
		
		if regexp.match(volume[1]) == None:
			pass
		
		else:
			try:
				volume[2] = int(volume[2]) / 1024 / 1024 # Used
				volume[3] = int(volume[3]) / 1024 / 1024 # Available
			
			except IndexError:
				pass
			
			except KeyError:
				pass
			
			disks_usage.append(volume)
	
	return disks_usage


def get_system_metrics( secret ):

	print datetime.datetime.now(), SECRET, 'Collecting system metrics..'

	uuid = UUID
	ip = _get_ip_address()
	loadavg = _get_sys_loadavg()
	uptime = _get_sys_uptime()
	cpu_usage = _get_sys_cpu()
	cpu_info = _get_sys_cpu_info()
	cpu_virtualization = _get_sys_cpu_virtualization()
	memory_usage = _get_memory_usage()
	physical_disks = _get_physical_disks()
	disks_usage = _get_disks_usage()
	
	system_metrics_json = {
		'uuid': uuid,
		'ip': ip,
		'secret': secret,
		'loadavg': loadavg,
		'uptime': uptime,
		'cpu_usage': cpu_usage,
		'cpu_info': cpu_info,
		'cpu_virtualization': cpu_virtualization,
		'memory_usage': memory_usage,
		'physical_disks': physical_disks,
		'disks_usage': disks_usage,
		# XXX system_metrics_json should include hypervisor networks as well
		'agent_version': AGENT_VERSION,
	}

	return system_metrics_json


def send_data( secret, api_call, data ):
	
	headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
	response = requests.post("http://"+API_SERVER+api_call, data=json.dumps(data), headers=headers)
	
	return response
	
	
if __name__=="__main__":

	os.system("clear")
		
	print "AGENT: v"+AGENT_VERSION
	print "Written By: jparicka"

	api_call = "/v10/activity/"
	activity = {
		'secret': SECRET,
		'agent_version': AGENT_VERSION,
		'uuid': UUID,
		'activity': "Agent v"+AGENT_VERSION+" has started."
	}
	send_data(SECRET,api_call,activity)
	
	try:
		if(not os.path.isdir("/data/disk1/iso/")):
			os.makedirs("/data/disk1/iso/")
	except:
		print 'You need to run the agent as user root.'
		sys.exit(0)
	
	
	while True:
	
		api_call = "/v10/ping/"
		system_metrics = get_system_metrics(SECRET)
		api_response = send_data(SECRET,api_call,system_metrics)
		
		if sys.platform == 'linux2':
			command = api_response.json
		elif sys.platform == 'darwin':
			command = api_response.json()
		
		command = command['command']
				
		if(command):

			# Using virsh!
			
			# install (w/autostart)
			# start
			# shutdown
			# force_shutdown
			# suspend
			# resume
			# save (backup)
			# restore
			# clone
			# add_volume
			# remove_volume
			# delete_vm (destroy, undefine, vol-delete)
			
			print datetime.datetime.now(), SECRET, '!! '*100
			print datetime.datetime.now(), SECRET, 'Received command:', command
			print datetime.datetime.now(), SECRET, 'sleeping 30'
			time.sleep(30)
			
		time.sleep(3)

	print "ze end."
