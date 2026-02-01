import { useState } from 'react';
import Login from './Login';
import Register from './Register';

export default function AuthPage() {
  const [isLogin, setIsLogin] = useState(true);

  if (isLogin) {
    return <Login onSwitchToRegister={() => setIsLogin(false)} />;
  }

  return <Register onSwitchToLogin={() => setIsLogin(true)} />;
}
