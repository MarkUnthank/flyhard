"""Synchronized native camera for the parking trial montage."""
import math
import queue
import subprocess
import carla
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from flyhard.parking import rectangle
from flyhard.shot_cameras import look_at
from flyhard.sponsor_view import SponsorView
from flyhard.steering_hud import draw_steering_readout


class ParkingTrialCamera:
    width=960
    height=720
    fov=68

    def __init__(self,env,asset,manifest):
        self.env,self.asset,self.manifest=env,asset,manifest
        self.sensors=[];self.queues=[];self.sponsor=None;self.writer=None;self.raw_writer=None;self.depth_writer=None
        self.font=ImageFont.truetype('assets/fonts/Geist.ttf',22)
        p=env.transform(-1,13).location;t=env.transform(0,1).location
        self.pose=look_at([p.x,p.y,15],[t.x,t.y,.6])
        self.inverse=np.linalg.inv(np.asarray(self.pose.get_matrix()))

    def begin(self,root,number):
        env=self.env
        if not self.sensors:
            for kind in ['rgb','depth']:
                bp=env.world.get_blueprint_library().find('sensor.camera.'+kind)
                for k,v in {'image_size_x':str(self.width),'image_size_y':str(self.height),'fov':str(self.fov),
                            'sensor_tick':'0','lens_k':'0','lens_kcube':'0'}.items():bp.set_attribute(k,v)
                if kind=='rgb':bp.set_attribute('motion_blur_intensity','0')
                sensor=env.world.spawn_actor(bp,self.pose);q=queue.Queue(maxsize=3)
                def receive(image,q=q):
                    try:q.put_nowait(image)
                    except queue.Full:
                        try:q.get_nowait()
                        except queue.Empty:pass
                        q.put_nowait(image)
                sensor.listen(receive);self.sensors.append(sensor);self.queues.append(q)
            box=env.ego.bounding_box.location
            self.sponsor=SponsorView(self.asset,self.manifest,[box.x,box.y,box.z],self.width,self.height)
            for _ in range(35):env.world.tick()
        for q in self.queues:
            while not q.empty():q.get_nowait()
        bay=np.array([[p.x,p.y,.035,1] for x,y in rectangle(0,0,0,env.case.length,env.case.width)
                      for p in [env.transform(x,y).location]])
        points=np.concatenate([a[None]+np.linspace(0,1,800)[:,None]*(b-a)[None] for a,b in zip(bay,np.roll(bay,-1,axis=0))])
        cp=points@self.inverse.T;f=self.width/(2*math.tan(math.radians(self.fov)/2))
        u=np.rint(self.width/2+f*cp[:,1]/np.maximum(cp[:,0],.01)).astype(int)
        v=np.rint(self.height/2-f*cp[:,2]/np.maximum(cp[:,0],.01)).astype(int)
        good=(cp[:,0]>.1)&(u>=2)&(u<self.width-2)&(v>=2)&(v<self.height-2)
        self.u,self.v,self.z=u[good],v[good],cp[good,0];self.number=number;self.frames=0;self.root=root
        def writer(name,crf):
            return subprocess.Popen(['ffmpeg','-nostdin','-v','error','-f','rawvideo','-pix_fmt','rgb24',
                '-s',f'{self.width}x{self.height}','-r','20','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast',
                '-crf',str(crf),'-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(root/name)],stdin=subprocess.PIPE)
        self.writer=writer('camera.mp4',19);self.raw_writer=writer('native-camera.mp4',15)
        # Keep packed CARLA depth bit-exact in one lossless file. Thousands of
        # individual PNG writes are expensive on the Pod's network filesystem.
        self.depth_writer=subprocess.Popen(['ffmpeg','-nostdin','-v','error','-f','rawvideo','-pix_fmt','rgb24',
            '-s',f'{self.width}x{self.height}','-r','20','-i','pipe:0','-an','-c:v','ffv1','-level','3',
            '-coder','1','-context','1','-g','1','-threads','2','-pix_fmt','bgr0',str(root/'native-depth.mkv')],stdin=subprocess.PIPE)

    def capture(self,env,rig,row):
        images=[]
        for q in self.queues:
            while True:
                image=q.get(timeout=60)
                if image.frame>=row['carla_frame']:
                    assert image.frame==row['carla_frame'];images.append(image);break
        assert images[0].timestamp==images[1].timestamp
        arrays=[np.frombuffer(im.raw_data,np.uint8).reshape(self.height,self.width,4)[:,:,:3][:,:,::-1].copy() for im in images]
        raw,d=arrays
        self.raw_writer.stdin.write(raw.tobytes())
        self.depth_writer.stdin.write(d.tobytes())
        d=d.astype(np.float32);depth=(d[:,:,0]+256*d[:,:,1]+65536*d[:,:,2])*(1000/16777215)
        visible=depth[self.v,self.u]>=self.z-.08;u,v=self.u[visible],self.v[visible]
        for dx in [-1,0,1]:
            for dy in [-1,0,1]:raw[v+dy,u+dx]=[217,190,92]
        relative=np.linalg.inv(np.asarray(row['vehicle_matrix']))@np.asarray(self.pose.get_matrix())
        raw,count=self.sponsor.render(relative,self.fov,raw,depth)
        canvas=Image.fromarray(raw);draw=ImageDraw.Draw(canvas)
        draw.rectangle((0,0,self.width,40),fill='black')
        gear={-1:'REVERSE',0:'NEUTRAL',1:'FORWARD'}[row['applied_controls']['gear']]
        draw.text((12,20),f'#{self.number:02}  {gear}',font=self.font,anchor='lm',fill='#eee')
        draw.text((self.width-12,20),f"{row['time']:.1f}s · {row['speed_m_s']*3.6:.1f} km/h",font=self.font,anchor='rm',fill='#eee')
        draw_steering_readout(canvas,requested_angle=row['requested_angle'],wheel_angle=row['wheel_angle'],applied_steer=row['applied_steer'])
        self.writer.stdin.write(np.asarray(canvas).tobytes());self.frames+=1
        row['camera']={'frame':images[0].frame,'timestamp':images[0].timestamp,'sponsor_pixels':count,
                       'width':self.width,'height':self.height,'fov':self.fov,'world_matrix':self.pose.get_matrix()}

    def finish(self):
        errors=[]
        for attr in ['writer','raw_writer','depth_writer']:
            writer=getattr(self,attr)
            if writer:
                try:writer.stdin.close()
                except BrokenPipeError:pass
                code=writer.wait();setattr(self,attr,None)
                if code:errors.append((attr,code))
        if errors:raise RuntimeError('Trial video encoding failed: '+str(errors))

    def close(self):
        self.finish()
        for sensor in self.sensors:sensor.stop();sensor.destroy()
        if self.sponsor:self.sponsor.close()
