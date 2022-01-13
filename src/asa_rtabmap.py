#!/usr/bin/env python3  
import rospy
import numpy as np
import tf
import tf2_ros
import tf2_msgs
from geometry_msgs.msg import Transform, PoseStamped, TransformStamped, Point, Quaternion
from std_srvs.srv import Empty
from std_msgs.msg import String
from rtabmap_ros.msg import *
from rtabmap_ros.srv import *
from nav_msgs.msg import Path
from sensor_msgs.msg import CompressedImage, Image, CameraInfo
import cv_bridge
import cv2

class Node:

    def __init__(self):

        rospy.init_node('asa_path')

        self.listener = tf.TransformListener()
        self.br = tf.TransformBroadcaster()
        self.buffer_rate = 1.0
        self.buffer_size = 100
        self.images_buffer = []
        self.current_node = None
        self.caminfo = None
        self.path = Path()
        self.mapToOdom = TransformStamped()
        self.mapToOdom.header.frame_id = 'map'
        self.mapToOdom.child_frame_id = 'odom2'

        rospy.Subscriber('mapData', MapData, self.callback1)
        rospy.Subscriber('image', Image, self.callback2)
        rospy.Subscriber('camera_info', CameraInfo, self.callback3)

        self.pub1 = rospy.Publisher('asa/image', Image, queue_size=1)
        self.pub2 = rospy.Publisher('asa/camera_info', CameraInfo, queue_size=1)
        rospy.Subscriber('/asa_rtabmap/get_map', String, self.handle_request)

        while not rospy.is_shutdown():
            self.main_loop()
            rospy.sleep(0.01)
            
        rospy.spin()

    def add_images_to_asa_buffer(self,mapToOdom):
        if len(self.images_buffer) == 0:
            return
        if self.caminfo is None:
            return

        for img_compressed in self.images_buffer:
            ps = self.interpolate_pose(self.path, img_compressed.header.stamp)
            if ps is None:
                continue
            img = img_compressed
            img.header.stamp = ps.header.stamp
            img.header.frame_id = 'asa_camera'
            self.pub1.publish(img)

            self.mapToOdom.header.stamp = img_compressed.header.stamp
            self.mapToOdom.transform = mapToOdom
            self.br.sendTransformMessage(self.mapToOdom)

            self.br.sendTransform((ps.pose.position.x, ps.pose.position.y, ps.pose.position.z),
                                  (ps.pose.orientation.x, ps.pose.orientation.y, ps.pose.orientation.z, ps.pose.orientation.w),
                                  ps.header.stamp,
                                  'asa_baselink',
                                  ps.header.frame_id)
             
            self.br.sendTransform((0,0,0),
                                  (0.5, -0.5 ,  0.5, -0.5),
                                  ps.header.stamp,
                                  'asa_camera',
                                  'asa_baselink')         
            
            self.caminfo.header.stamp = ps.header.stamp
            self.pub2.publish(self.caminfo)
        
        # self.images_buffer = abandoned_images        

    def callback1(self,msg):
        self.current_node.append(msg)

    def callback2(self,msg):
        if len(self.images_buffer) > 0:
            if msg.header.stamp.to_sec() - self.images_buffer[-1].header.stamp.to_sec() < 1/self.buffer_rate:
                return
        self.images_buffer.append(msg)
        if len(self.images_buffer) >= self.buffer_size:
            self.images_buffer.pop(0)

    def callback3(self,msg):
        self.caminfo = msg
      

    def main_loop(self):
          
        # req2 = GetMapRequest(global_=True,optimized=True,graphOnly=False)
        # srv = rospy.ServiceProxy('/rtabmap/rtabmap/get_map_data', GetMap)
        # res2 = srv(req2)
        mapToOdom = self.current_node.graph.mapToOdom
        node = self.current_node.nodes[0]
        pose = self.current_node.graph.poses[0]
        p = PoseStamped()
        p.pose = pose
        p.header.stamp = rospy.Time(node.stamp)
        self.path.poses.append(p)

        self.add_images_to_asa_buffer(mapToOdom)
        # self.images_buffer = []
        
    def interpolate_pose(self, path, stamp, frame_id='odom2'):
        if path is None or len(path.poses) == 0:
            return
        t = stamp.to_sec()
        ps = PoseStamped()
        ps.header.frame_id = frame_id
        ps.header.stamp = stamp
        for i in range(len(path.poses)-1):
            pose1 = path.poses[i]
            pose2 = path.poses[i+1]
            t1 = pose1.header.stamp.to_sec()
            t2 = pose2.header.stamp.to_sec()
            dt = t2 - t1
            if t >= t1 and t <= t2 and dt>0:                
                w = (t - t1) / dt
                ps.pose.position.x = pose1.pose.position.x + (pose2.pose.position.x - pose1.pose.position.x) * w
                ps.pose.position.y = pose1.pose.position.y + (pose2.pose.position.y - pose1.pose.position.y) * w
                ps.pose.position.z = pose1.pose.position.z + (pose2.pose.position.z - pose1.pose.position.z) * w
                q1 = np.array([pose1.pose.orientation.x,pose1.pose.orientation.y,pose1.pose.orientation.z,pose1.pose.orientation.w])
                q2 = np.array([pose2.pose.orientation.x,pose2.pose.orientation.y,pose2.pose.orientation.z,pose2.pose.orientation.w])
                q = tf.transformations.quaternion_slerp(q1, q2, w)
                ps.pose.orientation = Quaternion(q[0],q[1],q[2],q[3])

                return ps
        return

if __name__ == '__main__':
    Node()