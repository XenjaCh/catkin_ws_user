#!/usr/bin/env python

import sys
import time
import rospy
import matplotlib.pyplot as plt
import numpy as np
from std_msgs.msg import Int16
from std_msgs.msg import Float32

class SpeedController(object):
    
    def __init__(self, speed_arg, duration):
        Q_SIZE = 1000 # must be big, otherwise problems - car doesn't respond sometimes - ??? :(
        self.pub_speed = rospy.Publisher("/manual_control/speed", Int16, queue_size=Q_SIZE)
        time.sleep(1)
        self.speed_arg = speed_arg
        self.drive_duration = duration
        self.is_driving = False

    def start(self):
        # rospy.loginfo("starting...")
        # forward < 0 > backwards
        self.pub_speed.publish(self.speed_arg)
        self.is_driving = True

    def stop(self):
        # rospy.loginfo("stopping...")
        self.pub_speed.publish(0)
        self.is_driving = False

    def drive_journey(self):
        self.start()
        rospy.Timer(rospy.Duration(self.drive_duration), lambda _: self.stop(), oneshot=True)

class SteeringController(object):

    def __init__(self):
        self.pub_steer = rospy.Publisher("manual_control/steering", Int16, queue_size=100)
        time.sleep(1)

    def steer(self, degrees):
        ''' degrees==0 -> straight '''

        topic_arg = self.steering_angle_mapping(degrees)
        self.pub_steer.publish(topic_arg)

    def steering_angle_mapping(self, degrees):
        topic_args = [0, 30, 60, 90, 120, 150, 179]
        measured = [-23.4823835367, -16.2088298025, -4.10722402982,
            6.64525217941, 16.4196652944, 27.7491348616, 30.8972609386]
        
        deg_min = measured[0]
        deg_max = measured[-1]

        # culling high/low degrees
        if degrees < deg_min:
            degrees = deg_min
        elif degrees > deg_max:
            degrees = deg_max
        
        deg_interpolated = np.interp(degrees, measured, topic_args)

        return int(round(deg_interpolated)) # cca. +9 for simulator


class PController(object):

    def __init__(self, Kp, speed_ctrl, steer_ctrl):
        self.Kp = Kp
        self.speed_ctrl = speed_ctrl
        self.steer_ctrl = steer_ctrl
        
        # set_point == what we want=initial yaw-10deg
        self.set_point = 0.0

        # result from update()
        self.output = 0.0

        ''' first memasured yaw==desired-10 '''
        self.first_measure = True

        # we will be measuring only every Xth callback
        self.yaw_cb_inc = -1
        self.xth_cb = 10

        # set to time.time() in the beginning for plotting
        self.initial_time = 0.0
        self.initial_yaw = 0.0
        self.final_yaw = 0.0

        # for plotting
        self.time_arr = []
        self.squared_diffs = []
        self.heading_angles = []
        self.is_chart_plotted = False

    def add_time(self):
        cur_time = time.time()
        self.time_arr.append(cur_time-self.initial_time)

    def update(self, process_variable):
        ''' process_variable = what we measure '''

        error = self.set_point - process_variable
        self.squared_diffs.append(error**2)
        self.output = self.Kp * error
        print "Updated, output(steer degree)=%s" % self.output

    def update_and_steer(self, yaw_angle):
        self.update(yaw_angle)
        self.heading_angles.append(self.output)
        self.steer_ctrl.steer(self.output)

    def plot_squared_diffs_over_time(self):
        plt.figure(1)
        plt.subplot(211)
        plt.title('Initial Yaw=%s | Desired Yaw=%s | Final Yaw=%s' % (self.initial_yaw, self.set_point, self.final_yaw))
        plt.xlabel('')
        plt.ylabel('Squared yaw difference for Kp=%s' % self.Kp)
        plt.grid()
        plt.plot(self.time_arr, self.squared_diffs)

        plt.subplot(212)
        plt.title('Heading angle in degrees over time')
        plt.xlabel('Time [s]')
        plt.ylabel('Heading angle [deg]')
        plt.grid()
        plt.plot(self.time_arr, self.heading_angles)

        plt.show()

    def yaw_cb(self, yaw):
        # 1) (heading_angle) -> steer_command
        self.yaw_cb_inc += 1

        if self.yaw_cb_inc % self.xth_cb != 0: 
            return

        yaw_angle = yaw.data

        if self.first_measure:
            self.first_measure = False
            self.is_chart_plotted = False

            # desired yaw is -10 from the initial one
            self.set_point = yaw_angle - 10
            
            self.initial_yaw = yaw_angle
            print "INITIAL YAW=%s" % yaw_angle
            print "SET POINT=%s" % self.set_point
            
            self.steer_ctrl.steer(self.set_point)
            self.time_arr.append(0)
            self.initial_time = time.time()
            self.speed_ctrl.drive_journey() # Go!
            
            self.update_and_steer(yaw_angle)
            return

        self.add_time()
        print "Yaw: %s" % yaw_angle
        
        self.update_and_steer(yaw_angle)

        if not self.speed_ctrl.is_driving and not self.is_chart_plotted:
            self.final_yaw = yaw_angle
            self.plot_squared_diffs_over_time()
            self.is_chart_plotted = True
            rospy.signal_shutdown("Drive ended")


def main(args):
    rospy.init_node("p_control")

    K_P = 0.85
    SPEED_ARG = -180
    DRIVE_DURATION = 14 # less for sim - tooks too long otherwise

    speed_ctrl = SpeedController(SPEED_ARG, DRIVE_DURATION)
    steer_ctrl = SteeringController()
    p_controller = PController(K_P, speed_ctrl, steer_ctrl)

    rospy.Subscriber("model_car/yaw", Float32, p_controller.yaw_cb, queue_size=10)

    try:
        rospy.spin()
    except KeyboardInterrupt:
        print("Shutting down")


if __name__ == '__main__':
    main(sys.argv)