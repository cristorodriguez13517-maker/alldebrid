/* SHARKTV - reproductor HTML5 AllDebrid con activación explícita de audio para WebView */
(()=>{
 'use strict';
 const modal=document.getElementById('shark-player-modal');
 const video=document.getElementById('shark-player-video');
 const title=document.getElementById('shark-player-title');
 const closeButton=document.getElementById('shark-player-close');
 const status=document.getElementById('shark-player-status');
 const stage=modal&&modal.querySelector('.shark-player-stage');
 if(!modal||!video||!closeButton||!stage)return;

 // Botón propio: el toque del usuario desbloquea el audio en WebView/Android.
 let audioButton=document.getElementById('shark-player-audio');
 if(!audioButton){
  audioButton=document.createElement('button');
  audioButton.id='shark-player-audio';
  audioButton.type='button';
  audioButton.textContent='🔊 ACTIVAR SONIDO';
  audioButton.setAttribute('aria-label','Activar sonido del vídeo');
  Object.assign(audioButton.style,{
   position:'absolute',left:'50%',top:'50%',transform:'translate(-50%,-50%)',
   zIndex:'5',padding:'15px 22px',minHeight:'52px',border:'2px solid #fff',
   borderRadius:'12px',background:'#c90018',color:'#fff',fontSize:'17px',
   fontWeight:'700',boxShadow:'0 3px 18px #000',cursor:'pointer'
  });
  stage.style.position='relative';
  stage.appendChild(audioButton);
 }

 function cerrarReproductorAllDebrid(){
  video.pause();
  video.removeAttribute('src');
  video.load();
  modal.hidden=true;
  document.body.style.overflow='';
  status.textContent='';
  audioButton.hidden=true;
  if(document.fullscreenElement&&document.exitFullscreen){
   document.exitFullscreen().catch(()=>{});
  }
 }
 async function activarAudio(){
  // Estas operaciones ocurren directamente dentro del gesto táctil/clic.
  video.removeAttribute('muted');
  video.defaultMuted=false;
  video.muted=false;
  video.volume=1;
  try{
   await video.play();
   audioButton.hidden=true;
   status.textContent='';
  }catch(error){
   audioButton.hidden=false;
   status.textContent='El WebView no ha podido iniciar el audio. Puede que no admita el códec de sonido de este archivo.';
  }
 }
 audioButton.addEventListener('click',activarAudio);
 audioButton.addEventListener('touchend',event=>{
  event.preventDefault();
  activarAudio();
 },{passive:false});

 window.abrirReproductorAllDebrid=(url,nombre='')=>{
  let media;
  try{media=new URL(url,location.href);}catch(e){
   alert('El enlace de reproducción no es válido.');return;
  }
  if(media.protocol!=='https:'&&media.protocol!=='http:'){
   alert('El enlace de reproducción no es válido.');return;
  }
  video.pause();
  video.removeAttribute('src');
  video.load();
  title.textContent=nombre||'SHARKTV';
  status.textContent='Preparando vídeo…';
  audioButton.hidden=false;
  modal.hidden=false;
  document.body.style.overflow='hidden';
  video.controls=true;
  video.playsInline=true;
  video.setAttribute('playsinline','');
  video.setAttribute('webkit-playsinline','');
  video.removeAttribute('muted');
  video.defaultMuted=false;
  video.muted=false;
  video.volume=1;
  video.src=media.href;
  video.load();
  const playPromise=video.play();
  if(playPromise&&typeof playPromise.catch==='function'){
   playPromise.catch(async()=>{
    // Si el WebView bloquea autoplay con audio, iniciar imagen en silencio;
    // el usuario habilita el sonido con el botón explícito.
    video.muted=true;
    video.setAttribute('muted','');
    try{
     await video.play();
     status.textContent='Vídeo iniciado. Pulsa ACTIVAR SONIDO para escuchar.';
    }catch(e){
     status.textContent='Pulsa reproducir para iniciar el vídeo.';
    }
   });
  }
 };
 video.addEventListener('playing',()=>{
  if(!video.muted&&video.volume>0){
   audioButton.hidden=true;
   status.textContent='';
  }else{
   audioButton.hidden=false;
   status.textContent='Pulsa ACTIVAR SONIDO para escuchar.';
  }
 });
 video.addEventListener('volumechange',()=>{
  if(!video.muted&&video.volume>0){
   audioButton.hidden=true;
   status.textContent='';
  }
 });
 video.addEventListener('error',()=>{
  audioButton.hidden=false;
  const code=video.error&&video.error.code;
  status.textContent=code===4
   ?'El WebView no admite el formato de vídeo o alguno de sus códecs.'
   :'No se ha podido reproducir este vídeo. Comprueba la conexión o el formato.';
 });
 closeButton.addEventListener('click',cerrarReproductorAllDebrid);
 document.addEventListener('keydown',event=>{
  if(modal.hidden)return;
  const key=event.key;
  const code=event.keyCode||event.which;
  if(key==='Escape'||key==='Backspace'||code===4){
   event.preventDefault();
   cerrarReproductorAllDebrid();
  }
 },true);
 window.cerrarReproductorAllDebrid=cerrarReproductorAllDebrid;
})();